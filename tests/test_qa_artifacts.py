"""Offline tests for the per-run artifact writers. No browsers, no network."""

import csv
import dataclasses
import hashlib
import io
import json
from datetime import datetime, timezone

from jev_ultrafast.qa import artifacts
from jev_ultrafast.qa.contracts import (
    DEFAULT_MAX_STEPS,
    DEFECT_COLUMNS,
    MERMAID_SHA256,
    MERMAID_VERSION,
    Finding,
    PageEvent,
    RunConfig,
    RunContext,
)

STARTED_AT = datetime(2026, 9, 29, 9, 58, 0, tzinfo=timezone.utc).timestamp()


def event(step, *, operation="CLICK", target="12", label="Sign in", failing=False, executed=True, error=None):
    return PageEvent(
        step=step,
        timestamp_ms=1_780_000_000_000 + step * 1000,
        url="https://www.design-bakery.com/",
        title="Bakery",
        operation=operation,
        target=target,
        label=label,
        action_id=f"a{step}",
        executed=executed,
        page_changed=True,
        error=error,
        fingerprint=f"fp{step}",
        failing=failing,
    )


def finding(defect_id="D001", *, stage="playwright", kind="broken_link", severity="P1", status="confirmed",
            action="step 2: CLICK [5] Menu", evidence_refs=()):
    return Finding(
        defect_id=defect_id,
        stage=stage,
        kind=kind,
        severity=severity,
        title="Menu link is dead",
        url="https://www.design-bakery.com/menu",
        action=action,
        timestamp="2026-09-29T10:00:00Z",
        detail="HTTP 404 on click",
        confidence=0.9,
        status=status,
        evidence_refs=list(evidence_refs),
    )


def make_context(run_dir, *, events=(), findings=(), provenance=None, runner="laya", provider=None,
                 playwright=True, vision_mode="off"):
    config = RunConfig(
        target_url="https://www.design-bakery.com/",
        runner=runner,
        provider=provider,
        playwright=playwright,
        vision_mode=vision_mode,
    )
    context = RunContext(
        config=config,
        run_id="2026-09-29 www.design-bakery.com first look",
        run_dir=str(run_dir),
        started_at=STARTED_AT,
    )
    context.events.extend(events)
    context.findings.extend(findings)
    context.provenance.update(provenance or {})
    return context


# --- workflow.mmd ---------------------------------------------------------


def test_workflow_is_byte_identical_for_same_events(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    events = [event(1), event(2, operation="WAIT", target=None, label="")]
    first = artifacts.write_workflow(a, events)
    second = artifacts.write_workflow(b, list(events))
    assert first.read_bytes() == second.read_bytes()
    text = first.read_text(encoding="utf-8")
    assert text.startswith("flowchart TD\n")
    assert text.endswith("\n")


def test_workflow_node_shape_edges_and_terminal(tmp_path):
    text = artifacts.render_workflow([event(1), event(2, operation="WAIT", target=None, label="")])
    assert '    S1["1. CLICK #91;12#93; Sign in \u2192 www.design-bakery.com"]' in text
    assert '    S2["2. WAIT \u2192 www.design-bakery.com"]' in text
    assert "    S1 --> S2" in text
    assert "    S2 --> T" in text
    assert '    T(["done (2 steps)"])' in text
    single = artifacts.render_workflow([event(1)])
    assert '    T(["done (1 step)"])' in single
    assert "    S1 --> T" in single


def test_workflow_marks_failing_steps(tmp_path):
    text = artifacts.render_workflow([event(1), event(2, failing=True), event(3)])
    assert "    class S2 failing" in text
    assert "    classDef failing fill:#c0392b,color:#fff" in text
    assert '    T(["done (3 steps, 1 failing)"])' in text
    clean = artifacts.render_workflow([event(1), event(2)])
    assert "class S" not in clean
    assert "classDef" not in clean


def test_workflow_escapes_quotes_and_brackets():
    text = artifacts.render_workflow([event(1, label='Say "hi" [now]')])
    node = next(line for line in text.splitlines() if line.strip().startswith("S1["))
    inner = node.strip()[len('S1["'):-len('"]')]
    assert '"' not in inner
    assert "[" not in inner and "]" not in inner
    assert "#quot;" in inner
    assert "#91;" in inner and "#93;" in inner


def test_workflow_terminal_outcomes():
    done = artifacts.render_workflow([event(1), event(2)])
    assert "done (2 steps)" in done
    blocked_error = artifacts.render_workflow([event(1), event(2, error="net::ERR_ABORTED")])
    assert "blocked (2 steps)" in blocked_error
    blocked_unexecuted = artifacts.render_workflow([event(1), event(2, executed=False)])
    assert "blocked (2 steps)" in blocked_unexecuted
    assert "blocked (0 steps)" in artifacts.render_workflow([])
    capped = artifacts.render_workflow([event(step) for step in range(1, DEFAULT_MAX_STEPS + 1)])
    assert f"steps-limit ({DEFAULT_MAX_STEPS} steps)" in capped


def test_workflow_terminal_reason_from_explorer(tmp_path):
    short = [event(step) for step in range(1, 8)]
    assert "steps-limit (7 steps)" in artifacts.render_workflow(short, terminal="max_steps")
    pair = [event(1), event(2)]
    assert "decider-exhausted (2 steps)" in artifacts.render_workflow(pair, terminal="decider_exhausted")
    assert "browser-error (2 steps)" in artifacts.render_workflow(pair, terminal="browser_error")
    assert "blocked (2 steps)" in artifacts.render_workflow(pair, terminal="blocked")
    assert "done (2 steps)" in artifacts.render_workflow(pair, terminal="done")
    assert "done (2 steps)" in artifacts.render_workflow(pair, terminal="unknown-future-value")
    artifacts.write_workflow(tmp_path, short, terminal="max_steps")
    assert "steps-limit (7 steps)" in (tmp_path / "workflow.mmd").read_text(encoding="utf-8")


def test_events_json_keeps_field_order_and_is_stable(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    events = [event(1), event(2, failing=True)]
    first = artifacts.write_events(a, events)
    second = artifacts.write_events(b, list(events))
    assert first.read_bytes() == second.read_bytes()
    data = json.loads(first.read_text(encoding="utf-8"))
    assert list(data[0]) == [field.name for field in dataclasses.fields(PageEvent)]
    assert data[1]["failing"] is True
    assert data[0]["url"] == "https://www.design-bakery.com/"


# --- defects.csv ----------------------------------------------------------


def test_defects_csv_header_full_row_and_endings(tmp_path):
    refs = ["evidence/step 02 menu.png", "evidence/link 03 design-bakery.com.json"]
    artifacts.write_defects(tmp_path, [finding(evidence_refs=refs)])
    raw = (tmp_path / "defects.csv").read_text(encoding="utf-8")
    assert "\r" not in raw
    assert raw.endswith("\n")
    rows = list(csv.reader(io.StringIO(raw)))
    assert rows[0] == list(DEFECT_COLUMNS)
    assert rows[1] == [
        "D001",
        "playwright",
        "broken_link",
        "P1",
        "0.9",
        "confirmed",
        "https://www.design-bakery.com/menu",
        "step 2: CLICK [5] Menu",
        "2026-09-29T10:00:00Z",
        "Menu link is dead",
        "HTTP 404 on click",
        "evidence/step 02 menu.png;evidence/link 03 design-bakery.com.json",
    ]


def test_defects_csv_sorted_by_stage_then_id_regardless_of_input_order(tmp_path):
    findings = [
        finding("D002", stage="vision", status="candidate"),
        finding("D003", stage="explorer", status="candidate"),
        finding("D001", stage="explorer", status="candidate"),
    ]
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    artifacts.write_defects(a, findings)
    artifacts.write_defects(b, list(reversed(findings)))
    assert (a / "defects.csv").read_bytes() == (b / "defects.csv").read_bytes()
    rows = list(csv.reader(io.StringIO((a / "defects.csv").read_text(encoding="utf-8"))))
    assert [row[0] for row in rows[1:]] == ["D001", "D003", "D002"]


# --- run.json -------------------------------------------------------------


def test_run_json_whitelist_keeps_hostile_provenance_out(tmp_path):
    secrets = ["sk-live-abc123", "sk-secret-xyz", "nested-secret-value", "Bearer sk-live-abc123"]
    provenance = {
        "backend": "laya-local",
        "model": "laya-8b",
        "laya_criteria_flattening": "describe-v1",
        "max_options_per_question": 12,
        "playwright_stage": "on",
        "run_error": "explorer stopped: element e9 vanished mid-step",
        "explorer_terminal": "done",
        "vision_model": "qwen3-vl-235b",
        "vision_provider": "openrouter",
        "OPENROUTER_API_KEY": secrets[0],
        "api_key": secrets[1],
        "notes": {"deep": secrets[2]},
        "authorization": secrets[3],
    }
    (tmp_path / "evidence").mkdir()
    png = tmp_path / "evidence" / "step 01 home.png"
    png.write_bytes(b"\x89PNG fake")
    context = make_context(
        tmp_path,
        events=[event(1), event(2, failing=True)],
        findings=[finding(evidence_refs=["evidence/step 01 home.png"])],
        provenance=provenance,
    )
    artifacts.write_events(tmp_path, context.events)
    artifacts.write_workflow(tmp_path, context.events)
    artifacts.write_defects(tmp_path, context.findings)
    artifacts.write_run(tmp_path, context)
    raw = (tmp_path / "run.json").read_text(encoding="utf-8")
    for secret in secrets:
        assert secret not in raw
    assert "OPENROUTER_API_KEY" not in raw
    data = json.loads(raw)
    assert data["run_id"] == context.run_id
    assert data["started"] == "2026-09-29T09:58:00Z"
    assert data["finished"].endswith("Z")
    assert data["target_url"] == "https://www.design-bakery.com/"
    assert data["runner"] == "laya"
    assert data["provider"] is None
    assert data["decision"] == {"backend": "laya-local", "model": "laya-8b"}
    assert data["stages"] == {"playwright": "on", "vision": "off"}
    assert data["steps"] == 2
    assert data["findings"]["total"] == 1
    assert data["findings"]["by_status"] == {"candidate": 0, "confirmed": 1, "unverified": 0}
    assert data["findings"]["by_kind"]["broken_link"] == 1
    assert data["provenance"] == {
        "backend": "laya-local",
        "model": "laya-8b",
        "laya_criteria_flattening": "describe-v1",
        "max_options_per_question": 12,
        "run_error": "explorer stopped: element e9 vanished mid-step",
        "explorer_terminal": "done",
        "vision_model": "qwen3-vl-235b",
        "vision_provider": "openrouter",
    }
    assert data["renderer"] == {
        "version": MERMAID_VERSION,
        "sha256": MERMAID_SHA256,
        "url": f"https://cdn.jsdelivr.net/npm/mermaid@{MERMAID_VERSION}/dist/mermaid.min.js",
        "source": "jev_ultrafast/qa/assets/mermaid.INFO.txt",
    }
    assert data["tool"]["package"] == "0.1.0"
    assert data["tool"]["python"]
    evidence = data["evidence"]
    for name in ("defects.csv", "events.json", "workflow.mmd"):
        assert name in evidence
    assert evidence["evidence/step 01 home.png"] == hashlib.sha256(b"\x89PNG fake").hexdigest()


def test_run_json_provider_rules(tmp_path):
    laya = make_context(tmp_path / "laya")
    assert artifacts.run_summary(laya, tmp_path / "laya")["provider"] is None
    jev_default = make_context(tmp_path / "jev", runner="jev")
    assert artifacts.run_summary(jev_default, tmp_path / "jev")["provider"] == "openrouter"
    jev_named = make_context(tmp_path / "ts", runner="jev", provider="typesafe")
    assert artifacts.run_summary(jev_named, tmp_path / "ts")["provider"] == "typesafe"


def test_run_json_tolerates_missing_git(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("git not available")

    monkeypatch.setattr(artifacts.subprocess, "run", boom)
    context = make_context(tmp_path)
    artifacts.write_run(tmp_path, context)
    data = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))
    assert data["tool"]["git"] is None


def test_stage_table_variants(tmp_path):
    completed = make_context(tmp_path, provenance={"playwright_stage": "on"})
    assert artifacts.stage_table(completed) == {"playwright": "on", "vision": "off"}
    no_marker = make_context(tmp_path)
    assert artifacts.stage_table(no_marker) == {"playwright": "not-run", "vision": "off"}
    skipped = make_context(tmp_path, playwright=False)
    assert artifacts.playwright_stage_status(skipped) == "skipped"
    failed = make_context(tmp_path, provenance={"playwright_stage": "failed-setup"})
    assert artifacts.playwright_stage_status(failed) == "failed-setup"
    declined = make_context(tmp_path, vision_mode="openrouter", provenance={"vision_stage": "declined"})
    assert artifacts.vision_stage_status(declined) == "declined"
    no_model = make_context(tmp_path, vision_mode="ollama", provenance={"vision_stage": "skipped-no-model"})
    assert artifacts.vision_stage_status(no_model) == "skipped-no-model"
    ran = make_context(
        tmp_path,
        findings=[finding("D001", stage="vision", kind="visual", status="candidate")],
        vision_mode="openrouter",
        provenance={"vision_stage": "ran"},
    )
    assert artifacts.vision_stage_status(ran) == "ran(1)"
    reviewed = make_context(
        tmp_path,
        findings=[finding("D001", stage="vision", kind="visual", status="candidate")],
        vision_mode="openrouter",
        provenance={"vision_stage": "ran", "vision_reviewed": 3},
    )
    assert artifacts.vision_stage_status(reviewed) == "ran(3)"
    unrecorded = make_context(tmp_path, vision_mode="ollama")
    assert artifacts.vision_stage_status(unrecorded) == "not-run"


# --- metamorphic ----------------------------------------------------------


def test_relabel_and_renumber_preserve_defect_rows(tmp_path):
    findings = [finding("D001"), finding("D002", stage="explorer", status="candidate")]
    base_events = [event(1, label="Menu"), event(2, label="Sign in", target="12")]
    mutated_events = [event(1, label="Menu   "), event(2, label="  Sign in", target="47")]
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    artifacts.write_defects(a, findings)
    artifacts.write_defects(b, findings)
    assert (a / "defects.csv").read_bytes() == (b / "defects.csv").read_bytes()
    base_mmd = artifacts.render_workflow(base_events)
    mutated_mmd = artifacts.render_workflow(mutated_events)
    assert base_mmd != mutated_mmd
    assert base_mmd.count("\n") == mutated_mmd.count("\n")
    assert base_mmd.splitlines()[0] == mutated_mmd.splitlines()[0] == "flowchart TD"
