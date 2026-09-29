"""Seeded fuzz of the explorer loop and its dead-control detector.

Deterministic (seed 0), fully offline: a scripted fake browser and a queued
fake decider, tmp_path only. The dead-control oracle recomputes the expected
findings from the executed event stream plus generated metadata and compares
exactly; every other assertion is a loop invariant.
"""

import random
import re

from jev_ultrafast.qa import explorer as explorer_mod
from jev_ultrafast.qa.contracts import FINDING_KINDS, RunConfig, RunContext

CASES = 220
TARGET = "https://fuzz.test/"
TERMINALS = {"done", "blocked", "max_steps", "decider_exhausted", "browser_error"}
STEP_RE = re.compile(r"^step (\d+): ")


def strip_step(action):
    return STEP_RE.sub("", action)


class FuzzBrowser:
    def __init__(self, observations, act_error_step=None):
        self.observations = list(observations)
        self.act_error_step = act_error_step
        self.act_count = 0
        self.closed = False

    def observe(self, screenshot=False):
        if not self.observations:
            raise RuntimeError("observations exhausted")
        return self.observations.pop(0)

    def act(self, action, page, text=None):
        self.act_count += 1
        if self.act_error_step is not None and self.act_count == self.act_error_step:
            raise RuntimeError(f"injected act failure {self.act_count}")
        return {"executed": action["id"]}

    def close(self):
        self.closed = True


class FuzzDecider:
    name = "fuzz"

    def __init__(self, decisions, raise_at=None, raise_kind=ValueError):
        self.queue = list(decisions)
        self.raise_at = raise_at
        self.raise_kind = raise_kind
        self.popped = []

    def decide(self, state, goal, history):
        index = len(self.popped)
        if self.raise_at is not None and index == self.raise_at:
            raise self.raise_kind("injected decider failure")
        if not self.queue:
            raise StopIteration
        decision = self.queue.pop(0)
        self.popped.append(decision)
        return decision


def make_case(rng, index):
    n_actions = rng.randint(1, 6)
    actions = []
    for i in range(n_actions):
        kind = rng.choice(("click", "click", "click", "fill", "scroll", "wait"))
        label = f"label {i} {rng.choice(('open', 'close', 'next', 'back'))}"
        if kind == "click":
            actions.append(
                {"id": f"a{i}", "kind": kind, "label": label, "role": "button", "value": "", "node": 10 + i}
            )
        elif kind == "fill":
            actions.append(
                {"id": f"a{i}", "kind": kind, "label": label, "role": "textbox", "value": "", "node": 10 + i}
            )
        elif kind == "scroll":
            actions.append({"id": f"a{i}", "kind": kind, "label": label, "delta": 120})
        else:
            actions.append({"id": f"a{i}", "kind": kind, "label": label})

    # Element indices follow model.action_space: click/fill/select in node order.
    target_by_id = {}
    position = 0
    for action in actions:
        if action["kind"] in ("click", "fill", "select"):
            position += 1
            target_by_id[action["id"]] = str(position)

    pattern = rng.choice(("frozen", "changing", "mixed"))
    pool = [f"fp-{index}-p{j}" for j in range(rng.randint(1, 3))]
    max_steps = rng.randint(3, 12)

    def fingerprint(step):
        if pattern == "frozen":
            return f"fp-{index}-frozen"
        if pattern == "changing":
            return f"fp-{index}-s{step}"
        return rng.choice(pool)

    observations = []
    for step in range(max_steps + 3):
        url, title, text = TARGET, "Fuzz home", "plain content"
        if step > 0 and rng.random() < 0.15:
            url = f"{TARGET}page/{step}"
            if rng.random() < 0.5:
                title, text = "404 Not Found", "page not found"
        observations.append(
            {
                "url": url,
                "title": title,
                "text": text,
                "scroll": {"y": 0},
                "actions": actions,
                "fingerprint": fingerprint(step),
                "marker": "m",
                "page_key": "pk",
                "guards": {},
            }
        )

    decisions = []
    for _ in range(max_steps + 1):
        roll = rng.random()
        if roll < 0.10:
            decisions.append(
                rng.choice(
                    (
                        None,
                        {},
                        "CLICK",
                        42,
                        {"operation": None},
                        {"operation": "CLICK"},
                        {"choice": "ghost", "operation": "CLICK", "target": "99"},
                    )
                )
            )
            continue
        if roll < 0.18:
            decisions.append({"operation": rng.choice(("DONE", "BLOCKED"))})
            continue
        action = rng.choice(actions)
        if action["kind"] == "click":
            decision = {"choice": action["id"], "operation": "CLICK", "confidence": 0.7}
            if rng.random() < 0.5:
                decision["target"] = target_by_id[action["id"]]
        elif action["kind"] == "fill":
            decision = {"choice": action["id"], "operation": "TYPE_TEXT", "text": "x", "confidence": 0.7}
        else:
            decision = {"choice": action["id"], "operation": action["kind"].upper(), "confidence": 0.7}
        decisions.append(decision)

    return {
        "index": index,
        "pattern": pattern,
        "actions": actions,
        "observations": observations,
        "decisions": decisions,
        "max_steps": max_steps,
        "act_error_step": rng.randint(1, max_steps) if rng.random() < 0.2 else None,
        "raise_at": rng.randint(0, max_steps) if rng.random() < 0.2 else None,
        "raise_kind": rng.choice((ValueError, KeyError)),
        "kind_by_id": {action["id"]: action["kind"] for action in actions},
    }


def run_case(case, tmp_path):
    config = RunConfig(target_url=TARGET, max_steps=case["max_steps"])
    context = RunContext(config=config, run_id=f"fuzz-{case['index']}", run_dir=str(tmp_path), started_at=0.0)
    browser = FuzzBrowser(case["observations"], case["act_error_step"])
    decider = FuzzDecider(case["decisions"], case["raise_at"], case["raise_kind"])
    terminal = explorer_mod.Explorer(config, context, browser_factory=lambda url: browser, decider=decider).run()
    return context, browser, decider, terminal


def produces_no_event(decision):
    if not isinstance(decision, dict):
        return True
    operation = decision.get("operation")
    return operation in {"DONE", "BLOCKED"} or not operation


def expected_dead_controls(case, events):
    """Mirror the detector: pending click, two consecutive identical fingerprints."""
    kind_by_id = case["kind_by_id"]
    seen = set()
    cited = []
    pending = None
    executed = [event for event in events if event.executed]
    pre_fp = case["observations"][0]["fingerprint"]
    pre_url = case["observations"][0]["url"]
    for event in executed:
        if kind_by_id.get(event.action_id) == "click" and pending is None:
            index = f" [{event.target}]" if event.target else ""
            key = ("dead_control", pre_url, f'{event.operation}{index} "{event.label}"')
            pending = {"step": event.step, "fp": pre_fp, "key": key, "count": 0}
        if pending is not None:
            if event.fingerprint == pending["fp"]:
                pending["count"] += 1
                if pending["count"] >= 2:
                    if pending["key"] not in seen:
                        seen.add(pending["key"])
                        cited.append(pending["step"])
                    pending = None
            else:
                pending = None
        pre_fp = event.fingerprint
        pre_url = event.url
    return cited


def test_explorer_fuzz_invariants(tmp_path):
    rng = random.Random(0)
    cases = [make_case(rng, index) for index in range(CASES)]
    total_findings = 0
    for case in cases:
        context, browser, decider, terminal = run_case(case, tmp_path)

        assert terminal in TERMINALS
        assert context.provenance["explorer_terminal"] == terminal
        assert browser.closed

        for finding in context.findings:
            assert finding.kind in FINDING_KINDS
            assert finding.stage == "explorer"
            assert finding.status == "candidate"
        total_findings += len(context.findings)

        # Dedupe by (kind, url, action) holds across the whole finding list.
        keys = [(f.kind, f.url, strip_step(f.action)) for f in context.findings]
        assert len(keys) == len(set(keys))

        # dead_control matches the oracle exactly: present if and only if a CLICK
        # saw two consecutive identical fingerprints, never when pages change.
        actual = [f for f in context.findings if f.kind == "dead_control"]
        actual_steps = [int(STEP_RE.match(f.action).group(1)) for f in actual]
        assert actual_steps == expected_dead_controls(case, context.events)
        cited = set()
        for finding in context.findings:
            match = STEP_RE.match(finding.action)
            if match:
                cited.add(int(match.group(1)))
        assert {e.step for e in context.events if e.failing} == cited
        if case["pattern"] == "changing":
            assert actual == []

        # One event per decide-execute cycle; steps stay contiguous from 1.
        steps = [event.step for event in context.events]
        assert steps == list(range(1, len(steps) + 1))
        popped = decider.popped
        expected_events = len(popped) - (1 if popped and produces_no_event(popped[-1]) else 0)
        assert len(context.events) == expected_events
    assert total_findings > 0  # the seed generates real findings, not a silent no-op
