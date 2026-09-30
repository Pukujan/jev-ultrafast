"""Offline tests for the guided exploration loop: scripted fake browser, queued fake decider."""

import json
from pathlib import Path

import pytest

from jev_ultrafast.qa import explorer as explorer_mod
from jev_ultrafast.qa.contracts import RunConfig, RunContext


def make_actions():
    return [
        {"id": "e1", "kind": "click", "label": "Sign in", "role": "button", "value": "", "node": 20},
        {"id": "e2", "kind": "click", "label": "About", "role": "link", "value": "", "node": 21},
        {"id": "e3", "kind": "fill", "label": "Search", "role": "textbox", "value": "", "node": 22},
    ]


def make_page(url="https://example.test/", title="Home", text="Welcome to the example.",
              fingerprint="fp-home", actions=None):
    return {
        "url": url,
        "title": title,
        "text": text,
        "scroll": {"y": 0},
        "actions": actions if actions is not None else make_actions(),
        "fingerprint": fingerprint,
        "marker": "m",
        "page_key": "pk",
        "guards": {},
    }


class FakeBrowser:
    def __init__(self, observations, act_error=None):
        self.observations = list(observations)
        self.act_error = act_error
        self.act_calls = []
        self.closed = False

    def observe(self, screenshot=False):
        if not self.observations:
            raise RuntimeError("no scripted observation")
        return self.observations.pop(0)

    def act(self, action, page, text=None):
        if self.act_error is not None:
            raise self.act_error
        self.act_calls.append({"id": action["id"], "text": text})
        return {"executed": action["id"]}

    def close(self):
        self.closed = True


class FakeDecider:
    name = "fake"

    def __init__(self, decisions):
        self.queue = list(decisions)
        self.states = []
        self.histories = []

    def decide(self, state, goal, history):
        self.states.append(state)
        self.histories.append(list(history))
        if not self.queue:
            raise StopIteration
        return self.queue.pop(0)


def click(choice="e1", target="1", confidence=0.9, **extra):
    return {"choice": choice, "operation": "CLICK", "target": target, "confidence": confidence, **extra}


def build(tmp_path, observations, decisions, runner="laya", max_steps=60, act_error=None):
    config = RunConfig(target_url="https://example.test/", runner=runner, max_steps=max_steps)
    context = RunContext(config=config, run_id="run", run_dir=str(tmp_path), started_at=0.0)
    browser = FakeBrowser(observations, act_error=act_error)
    decider = FakeDecider(decisions)
    exp = explorer_mod.Explorer(config, context, browser_factory=lambda url: browser, decider=decider)
    return exp, context, browser, decider


def test_decider_is_required(tmp_path):
    config = RunConfig(target_url="https://example.test/")
    context = RunContext(config=config, run_id="run", run_dir=str(tmp_path), started_at=0.0)
    with pytest.raises(ValueError):
        explorer_mod.Explorer(config, context)


def test_dead_control_after_two_same_fingerprint_observations(tmp_path):
    page = make_page(fingerprint="fp-a")
    exp, context, browser, _ = build(tmp_path, [page, page, page], [click(), click(), {"operation": "DONE"}])
    assert exp.run() == "done"
    assert len(context.findings) == 1
    finding = context.findings[0]
    assert finding.stage == "explorer"
    assert finding.kind == "dead_control"
    assert finding.status == "candidate"
    assert finding.url == "https://example.test/"
    assert 'step 1: CLICK [1] "Sign in"' in finding.action
    assert context.events[0].failing is True
    assert context.events[1].failing is False
    assert browser.closed


def test_dead_control_is_deduped_by_kind_url_action(tmp_path):
    page = make_page(fingerprint="fp-a")
    exp, context, _, _ = build(tmp_path, [page] * 5, [click()] * 4 + [{"operation": "DONE"}])
    assert exp.run() == "done"
    assert len(context.findings) == 1
    assert [event.failing for event in context.events] == [True, False, False, False]


def test_changed_page_after_click_is_not_dead(tmp_path):
    pages = [make_page(fingerprint=f"fp-{i}") for i in range(3)]
    exp, context, _, _ = build(tmp_path, pages, [click(), click("e2", "2"), {"operation": "DONE"}])
    assert exp.run() == "done"
    assert context.findings == []


def test_broken_link_landing_stays_candidate(tmp_path):
    start = make_page(fingerprint="fp-a")
    missing = make_page(url="https://example.test/missing", title="404 Not Found",
                        text="Sorry, that page was not found.", fingerprint="fp-b")
    exp, context, _, _ = build(tmp_path, [start, missing], [click("e2", "2"), {"operation": "DONE"}])
    assert exp.run() == "done"
    assert len(context.findings) == 1
    finding = context.findings[0]
    assert finding.kind == "broken_link"
    assert finding.status == "candidate"
    assert finding.url == "https://example.test/missing"
    assert 'step 1: CLICK [2] "About"' in finding.action
    assert "HTTP status" in finding.detail
    assert context.events[0].page_changed is True
    assert context.events[0].failing is True


@pytest.mark.parametrize("title,text", [
    ("404 Not Found", "nothing here"),
    ("Internal Server Error", "something went wrong"),
    ("Service Unavailable", "please retry later"),
    ("Bad Gateway", "upstream failed"),
])
def test_error_page_patterns_raise_broken_link(tmp_path, title, text):
    start = make_page(fingerprint="fp-a")
    landing = make_page(url="https://example.test/next", title=title, text=text, fingerprint="fp-b")
    exp, context, _, _ = build(tmp_path, [start, landing], [click("e2", "2"), {"operation": "DONE"}])
    exp.run()
    assert [finding.kind for finding in context.findings] == ["broken_link"]


def test_http_server_style_error_body_is_detected(tmp_path):
    start = make_page(fingerprint="fp-a")
    landing = make_page(
        url="https://example.test/missing.html",
        title="Error response",
        text="Error code: 404. Message: File not found.",
        fingerprint="fp-b",
    )
    exp, context, _, _ = build(tmp_path, [start, landing], [click("e2", "2"), {"operation": "DONE"}])
    exp.run()
    assert [finding.kind for finding in context.findings] == ["broken_link"]


@pytest.mark.parametrize("title,text", [
    ("Pricing", "Over 500 plans and growing."),
    ("Search results", "No matches. Not found in our catalog."),
    ("About", "Serving 502 customers since 2020."),
])
def test_healthy_pages_mentioning_statuses_are_not_flagged(tmp_path, title, text):
    start = make_page(fingerprint="fp-a")
    landing = make_page(url="https://example.test/next", title=title, text=text, fingerprint="fp-b")
    exp, context, _, _ = build(tmp_path, [start, landing], [click("e2", "2"), {"operation": "DONE"}])
    exp.run()
    assert context.findings == []

def test_large_numbers_in_copy_are_not_an_error_page(tmp_path):
    start = make_page(fingerprint="fp-a")
    landing = make_page(url="https://example.test/catalog", title="Catalog",
                        text="4040 products found", fingerprint="fp-b")
    exp, context, _, _ = build(tmp_path, [start, landing], [click("e2", "2"), {"operation": "DONE"}])
    exp.run()
    assert context.findings == []


def test_act_exception_records_browser_error_candidate(tmp_path):
    page = make_page(fingerprint="fp-a")
    exp, context, browser, _ = build(
        tmp_path, [page, page], [click()], act_error=RuntimeError("CDP session closed")
    )
    assert exp.run() == "browser_error"
    assert len(context.findings) == 1
    finding = context.findings[0]
    assert finding.kind == "browser_error"
    assert finding.status == "candidate"
    assert "RuntimeError" in finding.detail
    event = context.events[-1]
    assert event.executed is False
    assert "CDP session closed" in event.error
    assert event.failing is True
    assert browser.closed


def test_first_observation_failure_is_a_setup_error(tmp_path):
    exp, context, _, decider = build(tmp_path, [], [click()])
    assert exp.run() == "browser_error"
    assert context.findings == []
    assert context.events == []
    assert decider.states == []
    assert "RuntimeError" in context.provenance["explorer_open_error"]


def test_browser_factory_failure_is_a_setup_error(tmp_path):
    config = RunConfig(target_url="https://example.test/")
    context = RunContext(config=config, run_id="run", run_dir=str(tmp_path), started_at=0.0)

    def factory(url):
        raise RuntimeError("daemon unreachable")

    exp = explorer_mod.Explorer(config, context, browser_factory=factory, decider=FakeDecider([]))
    assert exp.run() == "browser_error"
    assert context.findings == []
    assert "daemon unreachable" in context.provenance["explorer_open_error"]
    assert context.provenance["explorer_terminal"] == "browser_error"


@pytest.mark.parametrize("word", ["DONE", "BLOCKED"])
def test_terminal_decision_stops_without_events(tmp_path, word):
    exp, context, _, _ = build(tmp_path, [make_page()], [{"operation": word}])
    assert exp.run() == word.lower()
    assert context.events == []
    assert context.provenance["explorer_terminal"] == word.lower()


def test_max_steps_caps_the_walk(tmp_path):
    pages = [make_page(fingerprint=f"fp-{i}") for i in range(4)]
    exp, context, _, _ = build(tmp_path, pages, [click()] * 5, max_steps=2)
    assert exp.run() == "max_steps"
    assert [event.step for event in context.events] == [1, 2]
    assert all(not event.failing for event in context.events)


def test_decider_exhaustion_stops_after_last_decision(tmp_path):
    pages = [make_page(fingerprint=f"fp-{i}") for i in range(3)]
    exp, context, _, _ = build(tmp_path, pages, [click()])
    assert exp.run() == "decider_exhausted"
    assert len(context.events) == 1
    assert context.provenance["explorer_terminal"] == "decider_exhausted"


def test_choice_outside_the_snapshot_is_never_executed(tmp_path):
    exp, context, browser, _ = build(
        tmp_path, [make_page()], [click(choice="selector(.evil)", target="9")]
    )
    assert exp.run() == "decider_exhausted"
    assert browser.act_calls == []
    event = context.events[-1]
    assert event.executed is False
    assert event.error


def test_operation_and_target_resolve_through_action_space(tmp_path):
    pages = [make_page(fingerprint=f"fp-{i}") for i in range(2)]
    exp, context, browser, _ = build(
        tmp_path, pages, [{"operation": "CLICK", "target": "2", "confidence": 0.7}, {"operation": "DONE"}]
    )
    assert exp.run() == "done"
    assert browser.act_calls == [{"id": "e2", "text": None}]
    assert context.events[0].action_id == "e2"


def test_fill_passes_decider_text_to_the_browser(tmp_path):
    pages = [make_page(fingerprint=f"fp-{i}") for i in range(2)]
    fill = {"choice": "e3", "operation": "TYPE_TEXT", "target": "3", "text": "hello", "confidence": 0.8}
    exp, context, browser, _ = build(tmp_path, pages, [fill, {"operation": "DONE"}])
    assert exp.run() == "done"
    assert browser.act_calls == [{"id": "e3", "text": "hello"}]


def test_history_entries_carry_agent_compatible_keys(tmp_path):
    pages = [make_page(fingerprint=f"fp-{i}") for i in range(3)]
    exp, _, _, decider = build(tmp_path, pages, [click(), click(), {"operation": "DONE"}])
    exp.run()
    history = decider.histories[-1]
    assert len(history) == 2
    for entry in history:
        assert {"action", "kind", "text", "page_changed"} <= set(entry)
    assert history[0]["action"] == "Sign in"
    assert history[0]["kind"] == "click"
    assert history[0]["page_changed"] is True


def test_events_are_ordered_counted_and_tagged(tmp_path):
    pages = [make_page(fingerprint=f"fp-{i}") for i in range(4)]
    exp, context, _, _ = build(tmp_path, pages, [click()] * 3 + [{"operation": "DONE"}])
    exp.run()
    assert [event.step for event in context.events] == [1, 2, 3]
    timestamps = [event.timestamp_ms for event in context.events]
    assert timestamps == sorted(timestamps)
    assert all(event.runner == "laya" for event in context.events)
    assert all(event.confidence == 0.9 for event in context.events)
    assert all(event.action_id == "e1" for event in context.events)


def test_laya_provenance_records_flattening_and_terminal(tmp_path):
    exp, context, _, _ = build(tmp_path, [make_page()], [{"operation": "DONE"}], runner="laya")
    exp.run()
    assert context.provenance["explorer_terminal"] == "done"
    assert context.provenance["laya_criteria_flattening"] == "describe-v1"


def test_jev_provenance_has_no_flattening(tmp_path):
    exp, context, _, _ = build(tmp_path, [make_page()], [{"operation": "DONE"}], runner="jev")
    exp.run()
    assert context.provenance["explorer_terminal"] == "done"
    assert "laya_criteria_flattening" not in context.provenance
    assert all(event.runner == "jev" for event in context.events)


def _substantive_page(**kwargs):
    return make_page(**kwargs)


def _shell_page():
    # What a client-rendered site offers before its bundle mounts: no text and
    # only the scroll/wait pseudo-actions that every snapshot carries.
    return make_page(
        text="",
        actions=[
            {"id": "scroll_down", "kind": "scroll", "label": "Scroll down", "delta": 560},
            {"id": "wait", "kind": "wait", "label": "Wait for the page to update"},
        ],
    )


def test_settle_waits_past_the_empty_shell_before_deciding(tmp_path, monkeypatch):
    state = {"n": 0}

    def fake_monotonic():
        state["n"] += 1
        return state["n"] * 1.0  # advances 1s per check, inside the 10s budget

    monkeypatch.setattr(explorer_mod.time, "monotonic", fake_monotonic)
    slept = []
    monkeypatch.setattr(explorer_mod.time, "sleep", slept.append)
    shell, hydrated = _shell_page(), make_page(fingerprint="fp-real")
    browser = FakeBrowser([shell, shell, hydrated, hydrated, hydrated])
    decider = FakeDecider([click(), {"operation": "DONE"}])
    config = RunConfig(target_url="https://example.test/", runner="laya")
    context = RunContext(config=config, run_id="run", run_dir=str(tmp_path), started_at=0.0)
    exp = explorer_mod.Explorer(config, context, browser_factory=lambda url: browser, decider=decider)
    assert exp.run() == "done"
    assert context.provenance["explorer_settle"].startswith("settled after")
    assert decider.states[0]["text"], "the model was shown the empty shell"


def test_settle_times_out_without_hiding_the_run(tmp_path, monkeypatch):
    clock = {"now": 0.0}

    def fake_monotonic():
        value = clock["now"]
        clock["now"] += 4.0  # blows the 10s budget on the third look
        return value

    monkeypatch.setattr(explorer_mod.time, "monotonic", fake_monotonic)
    shell = _shell_page()
    exp, context, _, decider = build(tmp_path, [shell] * 6, [{"operation": "BLOCKED"}])
    assert exp.run() == "blocked"
    assert context.provenance["explorer_settle"].startswith("no substance after")
    assert decider.states[0]["text"] == ""  # the shell is still walked, and said so


def test_has_substance_needs_real_controls_or_text():
    assert explorer_mod._has_substance(make_page())
    assert not explorer_mod._has_substance(_shell_page())
    assert explorer_mod._has_substance({**_shell_page(), "text": "mounted"})


def test_zero_step_run_still_records_the_judgment(tmp_path):
    exp, context, _, _ = build(tmp_path, [make_page()], [{"operation": "DONE", "confidence": 0.42}])
    assert exp.run() == "done"
    assert context.events == []  # nothing executed
    lines = (Path(tmp_path) / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["operation"] == "DONE" and record["confidence"] == 0.42 and record["step"] == 1
    assert record["candidates"] == {"CLICK": 2, "TYPE_TEXT": 1}  # what the model was offered


def test_failed_decider_is_recorded_with_its_error(tmp_path):
    class BrokenDecider:
        name = "broken"

        def decide(self, state, goal, history):
            raise ValueError("Invalid Decisions response; no action executed.")

    config = RunConfig(target_url="https://example.test/", runner="jev")
    context = RunContext(config=config, run_id="run", run_dir=str(tmp_path), started_at=0.0)
    browser = FakeBrowser([make_page()])
    exp = explorer_mod.Explorer(config, context, browser_factory=lambda url: browser, decider=BrokenDecider())
    assert exp.run() == "decider_exhausted"
    record = json.loads((Path(tmp_path) / "decisions.jsonl").read_text(encoding="utf-8"))
    assert "Invalid Decisions response" in record["error"]


class StaleOnceBrowser(FakeBrowser):
    """Raises StalePage on the first action only, the way a mounting page does."""

    def __init__(self, observations):
        super().__init__(observations)
        self.strikes = 1

    def act(self, action, page, text=None):
        if self.strikes:
            self.strikes -= 1
            raise explorer_mod.StalePage("Page changed since this decision. Observe again.")
        return super().act(action, page, text=text)


def test_stale_action_is_retried_without_a_finding(tmp_path):
    first, second = make_page(fingerprint="fp-a"), make_page(fingerprint="fp-b")
    browser = StaleOnceBrowser([first, second, second, second])
    config = RunConfig(target_url="https://example.test/", runner="laya")
    context = RunContext(config=config, run_id="run", run_dir=str(tmp_path), started_at=0.0)
    decider = FakeDecider([click(), click(), {"operation": "DONE"}])
    exp = explorer_mod.Explorer(config, context, browser_factory=lambda url: browser, decider=decider)
    assert exp.run() == "done"
    assert context.findings == []  # a harness race is never reported as a site defect
    assert context.provenance["explorer_stale_retries"] == 1
    assert [event.step for event in context.events] == [1]  # the retried attempt costs no step
    lines = [json.loads(line) for line in (Path(tmp_path) / "decisions.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [line.get("error") for line in lines] == [None, "stale snapshot", None, None]


def test_permanently_flickering_page_stops_the_walk_cleanly(tmp_path):
    page = make_page()
    browser = FakeBrowser([page] * 12, act_error=explorer_mod.StalePage("Page changed since this decision."))
    config = RunConfig(target_url="https://example.test/", runner="laya")
    context = RunContext(config=config, run_id="run", run_dir=str(tmp_path), started_at=0.0)
    decider = FakeDecider([click()] * 8)
    exp = explorer_mod.Explorer(config, context, browser_factory=lambda url: browser, decider=decider)
    assert exp.run() == "stale_page"
    assert context.findings == []
    assert context.events == []
    assert context.provenance["explorer_stale_retries"] == explorer_mod.MAX_STALE_RECOVERIES + 1
    assert context.provenance["explorer_settle"].startswith("stale after")
