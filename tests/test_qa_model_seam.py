"""Offline pins for the model.py transport seam. The default OpenRouter path
stays byte-identical: env lookup at call time, three positional args to the
module-global post_json, unchanged body and error strings."""

import pytest

from jev_ultrafast import model

STATE = {
    "url": "https://x.test/flights",
    "title": "Flights",
    "text": "Where from?",
    "scroll": 0.0,
    "actions": [
        {"id": "a1", "kind": "click", "node": "n1", "label": "Round trip", "role": "button"},
        {"id": "a2", "kind": "fill", "node": "n2", "label": "Where from?", "role": "textbox"},
    ],
}

def valid_answer(criteria, pick):
    """One validated choice: pick is the argmax, probabilities sum to 1."""
    others = [key for key in criteria if key != pick]
    if not others:
        return {"choice": pick, "probabilities": {pick: 1.0}, "confidence": 1.0}
    share = 0.1 / len(others)
    probabilities = {key: share for key in others}
    probabilities[pick] = 0.9
    return {"choice": pick, "probabilities": probabilities, "confidence": 0.9}


def answers_for(body, operation="CLICK", target="1"):
    answers = {"operation": valid_answer(body["questions"]["operation"]["criteria"], operation)}
    for name, question in body["questions"].items():
        if name.endswith("_target") and name == operation.lower() + "_target":
            answers[name] = valid_answer(question["criteria"], target)
    return {"answers": answers, "model": "typesafe/jev-1.13", "usage": {}}


def test_default_choose_uses_three_positional_args(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    seen = {}

    def post(_url, _key, body):  # the pinned stand-in shape from tests/test_agent.py
        seen.update(url=_url, key=_key, body=body)
        return answers_for(body)

    monkeypatch.setattr(model, "post_json", post)
    decision = model.choose(STATE, "Depart from Zurich", [])
    assert seen["url"] == "https://openrouter.ai/api/alpha/decisions"
    assert seen["key"] == "test"
    assert decision["operation"] == "CLICK"
    assert decision["request"] == seen["body"]


def test_missing_key_error_string_unchanged(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError) as error:
        model.choose(STATE, "goal", [])
    assert str(error.value) == "OPENROUTER_API_KEY is required for Decisions; nothing executed."


def test_build_request_body_env_model_read_at_call_time(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODEL", "some/other-slug")
    body = model.build_request_body(STATE, "goal", [])
    assert body["model"] == "some/other-slug"
    monkeypatch.delenv("OPENROUTER_MODEL")
    assert model.build_request_body(STATE, "goal", [])["model"] == "typesafe/jev-1.13"


def test_build_request_body_explicit_slug_wins(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODEL", "env/slug")
    body = model.build_request_body(STATE, "goal", [], model_slug="local/model")
    assert body["model"] == "local/model"


def test_exports_kept_for_agent_and_tests():
    for name in ("post_json", "validate_choice", "action_space", "choose", "field_context", "field_text"):
        assert callable(getattr(model, name)), name
    import jev_ultrafast.agent  # noqa: F401  (import-time names must resolve)


class SpyTransport:
    name = "spy"

    def __init__(self):
        self.calls = []

    def prepare(self, body):
        prepared = dict(body)
        prepared["model"] = "local/model"
        return prepared

    def request(self, body):
        self.calls.append(body)
        return answers_for(body)


def test_decide_seam_order_and_request_field():
    transport = SpyTransport()
    decision = model.decide(transport, STATE, "goal", [])
    assert len(transport.calls) == 1
    assert transport.calls[0]["model"] == "local/model"  # the prepared body is what was sent
    assert decision["request"] == transport.calls[0]
    assert decision["operation"] == "CLICK"


def test_choose_accepts_explicit_transport():
    transport = SpyTransport()
    decision = model.choose(STATE, "goal", [], transport=transport)
    assert transport.calls and decision["operation"] == "CLICK"


def test_openrouter_transport_is_the_default_with_no_network(monkeypatch):
    monkeypatch.setattr(model, "post_json", lambda url, key, body: answers_for(body))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    decision = model.choose(STATE, "goal", [])
    assert isinstance(model.OpenRouterTransport(), object)
    assert decision["operation"] == "CLICK"
