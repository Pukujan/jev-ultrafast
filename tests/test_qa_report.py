"""Offline tests for the saved report builder. No browsers, no network."""

import dataclasses
import hashlib
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from jev_ultrafast.qa import artifacts, report
from jev_ultrafast.qa.contracts import Finding, PageEvent, RunConfig, RunContext

STARTED_AT = datetime(2026, 9, 29, 9, 58, 0, tzinfo=timezone.utc).timestamp()
PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-bytes"


def event(step, *, operation="CLICK", target="5", label="Menu", failing=False):
    return PageEvent(
        step=step,
        timestamp_ms=1_780_000_000_000 + step * 1000,
        url="https://www.design-bakery.com/",
        title="Bakery",
        operation=operation,
        target=target,
        label=label,
        action_id=f"a{step}",
        executed=True,
        page_changed=True,
        fingerprint=f"fp{step}",
        failing=failing,
    )


def finding(defect_id="D001", *, stage="playwright", kind="dead_control", status="confirmed"):
    return Finding(
        defect_id=defect_id,
        stage=stage,
        kind=kind,
        severity="P1",
        title="Menu button does nothing",
        url="https://www.design-bakery.com/",
        action="step 2: CLICK [5] Menu",
        timestamp="2026-09-29T10:00:00Z",
        detail="Two observations in a row showed the same page.",
        confidence=0.9,
        status=status,
        evidence_refs=["evidence/step 02 menu.png", "evidence/link 01 design-bakery.com.json"],
    )


def make_context(run_dir, *, events, findings, provenance=None, vision_mode="off"):
    config = RunConfig(target_url="https://www.design-bakery.com/", vision_mode=vision_mode)
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


def built_run(tmp_path, *, events=None, findings=None, provenance=None, vision_mode="off"):
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True)
    (run_dir / "evidence").mkdir()
    (run_dir / "evidence" / "step 02 menu.png").write_bytes(PNG_BYTES)
    events = events if events is not None else [event(1), event(2, failing=True)]
    findings = findings if findings is not None else [finding()]
    merged = {"backend": "laya-local", "model": "laya-8b"}
    merged.update(provenance or {})
    context = make_context(run_dir, events=events, findings=findings, provenance=merged, vision_mode=vision_mode)
    artifacts.write_events(run_dir, context.events)
    artifacts.write_workflow(run_dir, context.events)
    artifacts.write_defects(run_dir, context.findings)
    artifacts.write_run(run_dir, context)
    return run_dir, context


def test_report_inlines_chart_and_stays_offline(tmp_path):
    run_dir, context = built_run(tmp_path)
    path = report.build_report(run_dir, context)
    text = path.read_text(encoding="utf-8")
    mmd = (run_dir / "workflow.mmd").read_text(encoding="utf-8")
    assert html.escape(mmd) in text
    assert '<pre class="mermaid">' in text
    assert '<script src="mermaid.min.js"></script>' in text
    assert "mermaid.initialize({startOnLoad:true});" in text
    srcs = re.findall(r'<(?:script|link|img)\b[^>]*\bsrc="([^"]*)"', text)
    assert srcs
    assert all("http" not in src.lower() for src in srcs)
    hrefs = re.findall(r'\bhref="([^"]*)"', text)
    assert all("http" not in href.lower() for href in hrefs)
    assert "cdn.jsdelivr.net" not in text


def test_report_copies_renderer_assets(tmp_path):
    run_dir, context = built_run(tmp_path)
    report.build_report(run_dir, context)
    assets = Path(report.__file__).resolve().parent / "assets"
    for name in ("mermaid.min.js", "mermaid.INFO.txt"):
        copied = run_dir / name
        assert copied.exists()
        assert hashlib.sha256(copied.read_bytes()).hexdigest() == (
            hashlib.sha256((assets / name).read_bytes()).hexdigest()
        )


def test_report_never_says_pass(tmp_path):
    run_dir, context = built_run(tmp_path)
    text = report.build_report(run_dir, context).read_text(encoding="utf-8")
    assert "pass" not in text.lower()
    empty = tmp_path / "empty"
    empty.mkdir()
    empty_context = make_context(empty, events=[event(1)], findings=[])
    artifacts.write_workflow(empty, empty_context.events)
    empty_text = report.build_report(empty, empty_context).read_text(encoding="utf-8")
    assert "no findings recorded" in empty_text
    assert "pass" not in empty_text.lower()


def test_build_report_reindexes_run_json_evidence(tmp_path):
    run_dir, context = built_run(tmp_path)
    before = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))["evidence"]
    assert "report.html" not in before
    assert "mermaid.min.js" not in before
    report.build_report(run_dir, context)
    after = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))["evidence"]
    for name in ("report.html", "mermaid.min.js", "mermaid.INFO.txt", "defects.csv", "events.json", "workflow.mmd"):
        assert name in after
    assert after["report.html"] == hashlib.sha256((run_dir / "report.html").read_bytes()).hexdigest()
    assert after["mermaid.min.js"] == hashlib.sha256((run_dir / "mermaid.min.js").read_bytes()).hexdigest()


def test_report_banner_counts(tmp_path):
    run_dir, context = built_run(tmp_path)
    text = report.build_report(run_dir, context).read_text(encoding="utf-8")
    assert "1 finding: 1 confirmed, 0 candidate" in text
    two = tmp_path / "two"
    two.mkdir()
    findings = [finding("D001"), finding("D002", stage="explorer", kind="browser_error", status="candidate")]
    context_two = make_context(two, events=[event(1), event(2, failing=True)], findings=findings)
    artifacts.write_workflow(two, context_two.events)
    text_two = report.build_report(two, context_two).read_text(encoding="utf-8")
    assert "2 findings: 1 confirmed, 1 candidate" in text_two


def test_report_vision_lines(tmp_path):
    run_dir, context = built_run(tmp_path)
    text = report.build_report(run_dir, context).read_text(encoding="utf-8")
    assert "vision not run" in text
    declined_run, declined_ctx = built_run(
        tmp_path / "declined",
        vision_mode="openrouter",
        provenance={"vision_stage": "declined"},
    )
    declined_text = report.build_report(declined_run, declined_ctx).read_text(encoding="utf-8")
    assert "vision was offered and declined" in declined_text
    no_model_run, no_model_ctx = built_run(
        tmp_path / "nomodel",
        vision_mode="ollama",
        provenance={"vision_stage": "skipped-no-model"},
    )
    no_model_text = report.build_report(no_model_run, no_model_ctx).read_text(encoding="utf-8")
    assert "vision skipped: no local vision model installed" in no_model_text
    ran_run, ran_ctx = built_run(
        tmp_path / "ran",
        findings=[finding("D001"), finding("D002", stage="vision", kind="visual", status="candidate")],
        vision_mode="openrouter",
        provenance={"vision_stage": "ran", "vision_provider": "openrouter", "vision_model": "qwen3-vl-235b"},
    )
    ran_text = report.build_report(ran_run, ran_ctx).read_text(encoding="utf-8")
    assert "vision ran via openrouter qwen3-vl-235b and added 1 finding" in ran_text


def test_report_defect_anchors_and_failing_step_links(tmp_path):
    run_dir, context = built_run(tmp_path)
    text = report.build_report(run_dir, context).read_text(encoding="utf-8")
    assert 'id="D001"' in text
    assert 'href="#D001"' in text
    assert "step 2 \u2192" in text
    assert "step 2: CLICK [5] Menu" in text
    assert "https://www.design-bakery.com/" in text


def test_report_evidence_thumbnails_reference_run_folder_files(tmp_path):
    run_dir, context = built_run(tmp_path)
    text = report.build_report(run_dir, context).read_text(encoding="utf-8")
    assert '<img class="thumb" src="evidence/step%2002%20menu.png"' in text
    assert "<code>evidence/link 01 design-bakery.com.json</code>" in text
    assert (run_dir / "evidence" / "step 02 menu.png").read_bytes() == PNG_BYTES


def test_report_provenance_appendix_and_secret_safety(tmp_path):
    run_dir, context = built_run(
        tmp_path,
        provenance={"VISION_API_KEY": "sk-vision-secret-999", "laya_criteria_flattening": "describe-v1"},
    )
    text = report.build_report(run_dir, context).read_text(encoding="utf-8")
    assert "sk-vision-secret-999" not in text
    assert "laya-local" in text
    assert "laya-8b" in text
    assert "describe-v1" in text
    assert "2026-09-29 www.design-bakery.com first look" in text
    assert f"mermaid {artifacts.MERMAID_VERSION}" in text
    assert "<h2>Provenance</h2>" in text


def test_report_without_run_json_falls_back_to_summary(tmp_path):
    run_dir, context = built_run(tmp_path)
    (run_dir / "run.json").unlink()
    text = report.build_report(run_dir, context).read_text(encoding="utf-8")
    assert "laya-local" in text
    assert "1 finding: 1 confirmed, 0 candidate" in text


def test_metamorphic_relabel_preserves_findings_links_and_evidence(tmp_path):
    run_dir, context = built_run(tmp_path)
    text_before = report.build_report(run_dir, context).read_text(encoding="utf-8")
    mutated = [dataclasses.replace(e, target="99", label=e.label + "  ") for e in context.events]
    artifacts.write_workflow(run_dir, mutated)
    context_two = make_context(
        run_dir,
        events=mutated,
        findings=context.findings,
        provenance=dict(context.provenance),
    )
    text_after = report.build_report(run_dir, context_two).read_text(encoding="utf-8")
    for needle in (
        'id="D001"',
        'href="#D001"',
        'src="evidence/step%2002%20menu.png"',
        "1 finding: 1 confirmed, 0 candidate",
    ):
        assert needle in text_before
        assert needle in text_after
    assert (run_dir / "evidence" / "step 02 menu.png").exists()
    assert text_before != text_after
    mutated_mmd = (run_dir / "workflow.mmd").read_text(encoding="utf-8")
    assert html.escape(mutated_mmd) in text_after


def test_open_report_uses_file_uri(tmp_path, monkeypatch):
    run_dir, context = built_run(tmp_path)
    report.build_report(run_dir, context)
    opened = []
    monkeypatch.setattr(report.webbrowser, "open", lambda url: opened.append(url))
    report.open_report(run_dir)
    assert len(opened) == 1
    assert opened[0].startswith("file://")
    assert opened[0].endswith("report.html")
