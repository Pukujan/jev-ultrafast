"""Offline tests for the OpenJev-on-Ollama decision arm.

No network: every scoring call goes through an injected poster that stands in
for Ollama's /api/generate reply. Covers the training-contract prompt shape,
softmax normalization over candidate labels, the 2-16 candidate cap with
coarse-to-fine chunks, the loopback guard, and the Jev-shaped answers the
shared validator consumes.
"""

import json
import math

import pytest

from jev_ultrafast import model
from jev_ultrafast.qa import openjev


class Recorder:
    """Serve queued logprob tables, one per scoring call; keep the payloads."""

    def __init__(self, tables):
        self.calls = []
        self.tables = list(tables)

    def __call__(self, payload):
        self.calls.append(payload)
        table = self.tables.pop(0)
        top = [{"token": token, "logprob": value} for token, value in table.items()]
        return {"response": max(table, key=table.get), "logprobs": [{"top_logprobs": top}]}


def choose(ids, descriptions, recorder, limit=openjev.MAX_CANDIDATES):
    return openjev.choose_question("state", "instructions", ids, descriptions, post=recorder, model="m", limit=limit)


def test_render_prompt_matches_the_training_contract():
    prompt = openjev.render_prompt("page state", "Pick one.", ["first", "second"])
    assert prompt.startswith("Shared state:\npage state\n\n")
    assert prompt.endswith("\nReturn only the selected letter: A, B.\nAnswer:")
    task = json.loads(prompt.split("\n\n", 1)[1].rsplit("\nReturn only", 1)[0])
    assert task["primitive"] == "choice"
    assert task["instructions"] == "Pick one."
    assert task["criteria"] == [
        {"description": "first", "label": "A"},
        {"description": "second", "label": "B"},
    ]


def test_small_choice_normalizes_over_candidates():
    answer = choose(["1", "2"], ["one", "two"], Recorder([{"A": -0.5, "B": -2.5}]))
    expected = math.exp(-0.5) / (math.exp(-0.5) + math.exp(-2.5))
    assert answer["choice"] == "1"
    assert answer["confidence"] == pytest.approx(expected, abs=1e-6)
    assert answer["probabilities"]["1"] == pytest.approx(expected, abs=1e-6)
    assert sum(answer["probabilities"].values()) == pytest.approx(1.0, abs=1e-5)
    assert answer["distribution_complete"] is True


def test_unseen_label_sits_below_every_reported_one():
    answer = choose(["1", "2", "3"], ["a", "b", "c"], Recorder([{"A": -0.1, "Z": -3.0}]))
    assert answer["distribution_complete"] is False
    assert answer["choice"] == "1"
    unseen = answer["probabilities"]["2"]
    assert 0 < unseen < answer["probabilities"]["1"]
    assert sum(answer["probabilities"].values()) == pytest.approx(1.0, abs=1e-5)


def test_wide_question_splits_coarse_to_fine_and_stays_normalized():
    count = 35
    ids = [str(index) for index in range(count)]
    descriptions = [f"element {index}" for index in range(count)]
    chunks = openjev._interleaved(count, openjev.MAX_CANDIDATES)
    assert [len(chunk) for chunk in chunks] == [12, 12, 11]
    tables = [{"A": -5.0, "B": -5.0, "C": -0.2} for _ in chunks]
    tables.append({"A": -4.0, "B": -0.1, "C": -4.0})  # chunk 1's winner takes the final pass
    recorder = Recorder(tables)
    answer = choose(ids, descriptions, recorder)
    assert len(recorder.calls) == len(chunks) + 1  # one pass per chunk, then the winners
    assert sum(answer["probabilities"].values()) == pytest.approx(1.0, abs=1e-5)
    assert len(answer["probabilities"]) == count
    assert answer["choice"] == ids[chunks[1][2]]  # label C inside chunk 1
    winner_share = answer["probabilities"][answer["choice"]]
    assert winner_share == max(answer["probabilities"].values())
    assert answer["probabilities"][ids[chunks[0][0]]] < winner_share


def test_one_option_question_needs_no_model_call():
    recorder = Recorder([])
    answer = choose(["only"], ["one"], recorder)
    assert answer == {
        "choice": "only",
        "confidence": 1.0,
        "probabilities": {"only": 1.0},
        "distribution_complete": True,
    }
    assert recorder.calls == []


def test_no_candidates_raises():
    with pytest.raises(ValueError):
        choose([], [], Recorder([]))


def test_only_reported_labels_get_mass_the_rest_take_the_global_floor():
    # Ollama's 20 slots are mostly non-letter tokens; unreported candidate
    # labels must sit below the lowest probability the server showed at all,
    # not below the lowest reported label, or a confident answer would
    # fabricate half of its own mass.
    reported = {"A": -0.05, "B": -3.0, "the": -6.0, " ": -6.5, "a": -7.0}
    answer = choose([str(n) for n in range(1, 7)], [f"e{n}" for n in range(6)], Recorder([reported]))
    assert answer["probabilities"]["1"] == pytest.approx(0.94899, abs=1e-4)
    assert max(answer["probabilities"][key] for key in ("3", "4", "5", "6")) < 0.002
    assert sum(answer["probabilities"].values()) == pytest.approx(1.0, abs=1e-5)


def test_recursion_covers_more_candidates_than_one_round_of_winners():
    # 300 options need 19 first-round chunks; 19 winners exceed the 16-label
    # cap, so the pass must recurse: 19 chunks, then 2 chunk-of-winners calls,
    # then 1 final pass.
    ids = [str(index) for index in range(300)]
    descriptions = [f"element {index}" for index in ids]
    level_one = openjev._interleaved(300, openjev.MAX_CANDIDATES)
    level_two = openjev._interleaved(len(level_one), openjev.MAX_CANDIDATES)
    tables = [{"A": -5.0, "B": -0.01} for _ in range(len(level_one) + len(level_two) + 1)]
    recorder = Recorder(tables)
    answer = choose(ids, descriptions, recorder)
    assert len(recorder.calls) == len(level_one) + len(level_two) + 1 == 22
    assert len(answer["probabilities"]) == 300
    assert sum(answer["probabilities"].values()) == pytest.approx(1.0, abs=1e-4)
    # B wins every round, so the promoted option is the B-path through each
    # interleaved split: replay the same structure instead of hardcoding.
    winners_one = [[ids[index] for index in chunk][1] for chunk in level_one]
    winners_two = [[winners_one[index] for index in chunk][1] for chunk in level_two]
    assert answer["choice"] == winners_two[1]

def test_answers_pass_the_shared_validator():
    answer = choose(["CLICK", "DONE"], ["click something", "finish"], Recorder([{"A": -0.2, "B": -2.0}]))
    assert model.validate_choice(answer, ["CLICK", "DONE"])["choice"] == "CLICK"


def test_base_url_stays_on_loopback():
    assert openjev.base_url("127.0.0.1:11500") == "http://127.0.0.1:11500"
    assert openjev.base_url("localhost") == "http://localhost"
    with pytest.raises(openjev.OpenJevUnavailable) as caught:
        openjev.base_url("https://elsewhere.example")
    assert "loopback" in str(caught.value)


def test_env_names_the_endpoint_and_model(monkeypatch):
    monkeypatch.setenv(openjev.OPENJEV_MODEL_ENV, "local/openjev-test:q8")
    monkeypatch.setenv(openjev.OPENJEV_BASE_URL_ENV, "127.0.0.1:11500")
    transport = openjev.OpenJevTransport(poster=Recorder([]))
    assert transport.model_slug == "local/openjev-test:q8"
    assert transport.base == "http://127.0.0.1:11500"
    assert transport.endpoint == "http://127.0.0.1:11500/api/generate"
    assert transport.name == "openjev"
    assert transport.prepare({"body": 1}) == {"body": 1}


def build_body():
    return {
        "model": "ignored-by-this-arm",
        "state": {
            "page": {"url": "https://x.test", "title": "T", "text": "hello world"},
            "elements": [],
            "recent_actions": [],
        },
        "questions": {
            "operation": {
                "type": "choice",
                "criteria": {"CLICK": {"element": "[1] Sign in (button)"}, "DONE": {"element": "finish up"}},
                "instructions": {"goal": "g", "rules": ["r1", "r2"]},
            },
            "click_target": {
                "type": "choice",
                "criteria": {"1": {"element": "[1] Sign in (button)", "role": "button", "current_value": "x"}},
                "instructions": "which element",
            },
        },
    }


def test_transport_rebuilds_jev_answers_from_two_questions():
    recorder = Recorder([{"A": -3.0, "B": -0.2}, {}])  # operation -> DONE; target single-option needs no call
    transport = openjev.OpenJevTransport(poster=recorder)
    result = transport.request(build_body())
    assert result["model"] == transport.model_slug
    answers = result["answers"]
    assert set(answers) == {"operation", "click_target"}
    assert answers["operation"]["choice"] == "DONE"
    assert answers["click_target"]["choice"] == "1"
    for answer in answers.values():
        assert sum(answer["probabilities"].values()) == pytest.approx(1.0, abs=1e-5)
    assert len(recorder.calls) == 1
    assert transport.question_meta == {
        "operation": {"candidates": 2, "distribution_complete": True},
        "click_target": {"candidates": 1, "distribution_complete": True},
    }


def test_request_body_carries_no_auth_and_uses_the_raw_contract():
    sent = Recorder([{"A": -0.1, "B": -2.0}])
    transport = openjev.OpenJevTransport(poster=sent)
    transport.request(build_body())
    payload = sent.calls[0]
    assert payload["raw"] is True and payload["stream"] is False and payload["logprobs"] is True
    assert payload["options"]["num_predict"] == 1
    assert "<th" + "ink>\n\n</th" + "ink>" in payload["prompt"]  # trained no-thinking prefill
    assert payload["prompt"].startswith("<|im_start|>user\nShared state:")


def test_preflight_refuses_a_closed_port_without_touching_the_browser():
    with pytest.raises(openjev.OpenJevUnavailable):
        openjev.OpenJevTransport(url="http://127.0.0.1:9").preflight()


def test_preflight_warms_the_model_and_reports_the_load():
    seen = []

    def poster(payload):
        seen.append(payload)
        return {"response": "A", "logprobs": [{"top_logprobs": [{"token": "A", "logprob": -0.1}]}]}

    transport = openjev.OpenJevTransport(
        poster=poster,
        getter=lambda path: {"version": "0.34.4"}
        if path.endswith("/api/version")
        else {"models": [{"name": transport_model()}]},
    )
    info = transport.preflight()
    assert info["model"] == transport_model() and info["version"] == "0.34.4"
    assert "load_ms" in info and len(seen) == 1  # one warm-up scoring call


def transport_model():
    return openjev.OPENJEV_DEFAULT_MODEL


def test_transport_reports_unreachable_server_from_request(monkeypatch):
    transport = openjev.OpenJevTransport(url="http://127.0.0.1:9")
    body = build_body()
    body["questions"].pop("click_target")
    with pytest.raises(openjev.OpenJevUnavailable) as caught:
        transport.request(body)
    assert "127.0.0.1:9" in str(caught.value)


def test_missing_logprobs_fail_closed_instead_of_guessing():
    def empty(payload):
        return {"response": "?"}

    with pytest.raises(openjev.OpenJevUnavailable):
        openjev.choose_question("s", "i", ["1", "2"], ["a", "b"], post=empty, model="m")


def test_decider_reuses_the_shared_decide_tail(monkeypatch):
    calls = []

    class FakeTransport:
        name = "openjev"
        model_slug = "fake/openjev"

        def prepare(self, body):
            calls.append(body)
            return body

        def request(self, body):
            # Mirror the real contract: answer every question the body asked,
            # over exactly the criteria keys it offered.
            answers = {}
            for name, question in body["questions"].items():
                ids = list(question["criteria"])
                picks = {option_id: round(1.0 / len(ids), 6) for option_id in ids}
                calls.append(ids[0])
                answers[name] = {"choice": ids[0], "confidence": picks[ids[0]], "probabilities": picks}
            return {"answers": answers, "model": "fake/openjev"}

    decider = openjev.openjev_decider(transport=FakeTransport())
    state = {"actions": [], "url": "https://x.test", "title": "t", "text": "", "history": []}
    decision = decider.decide(state, "goal", [])
    assert decision["operation"] == calls[-1]  # the fake's first offered operation
    assert decider.name == "openjev" and decider.model_slug == "fake/openjev"
