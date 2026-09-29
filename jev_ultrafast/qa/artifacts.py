"""Per-run artifact writers: defects.csv, events.json, workflow.mmd, run.json.

Every writer is a pure, deterministic function of the run context, so a
rerun over the same events produces byte-identical files. run.json is the
one exception: it records wall-clock finish time, tool versions, and file
hashes. Secret safety comes from a whitelist: run.json only ever carries
the provenance keys named in PROVENANCE_TEXT_KEYS / PROVENANCE_INT_KEYS,
so arbitrary provenance values (or credentials stored near them) cannot
reach disk. JUF-0003 / issue #9.
"""

from __future__ import annotations

import csv
import dataclasses
import hashlib
import json
import platform
import subprocess
import time
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .contracts import (
    ARTIFACT_DEFECTS,
    ARTIFACT_EVENTS,
    ARTIFACT_RUN,
    ARTIFACT_WORKFLOW,
    DEFAULT_MAX_STEPS,
    DEFECT_COLUMNS,
    FINDING_KINDS,
    FINDING_STATUSES,
    JEV_DEFAULT_PROVIDER,
    MERMAID_SHA256,
    MERMAID_VERSION,
    RUNNER_LAYA,
    Finding,
    PageEvent,
    RunContext,
)

PACKAGE_VERSION = "0.1.0"
RENDERER_URL = f"https://cdn.jsdelivr.net/npm/mermaid@{MERMAID_VERSION}/dist/mermaid.min.js"
RENDERER_SOURCE = "jev_ultrafast/qa/assets/mermaid.INFO.txt"

# Provenance keys allowed into run.json, by expected type. Anything else
# in context.provenance is dropped, never echoed.
PROVENANCE_TEXT_KEYS = ("backend", "model", "laya_criteria_flattening", "tracing_mode")
PROVENANCE_INT_KEYS = ("max_options_per_question",)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_text(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _write_json(path: Path, payload: dict) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def _iso_utc(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def write_events(run_dir: Path | str, events: Iterable[PageEvent]) -> Path:
    """Write events.json: every PageEvent as an object, field-declaration key order."""
    path = Path(run_dir) / ARTIFACT_EVENTS
    payload = [dataclasses.asdict(event) for event in events]
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    return path


# --- workflow.mmd ---------------------------------------------------------


def _escape_mermaid(text: str) -> str:
    """Escape label text for a quoted Mermaid node using Mermaid's own entities."""
    return text.replace('"', "#quot;").replace("[", "#91;").replace("]", "#93;")


def _event_label(event: PageEvent) -> str:
    parsed_host = ""
    if event.url:
        parsed = urlparse(event.url)
        parsed_host = parsed.hostname or parsed.netloc
    host = parsed_host or event.url
    parts = [f"{event.step}. {event.operation.upper()}"]
    if event.target is not None:
        parts.append(f"[{event.target}]")
    if event.label:
        parts.append(event.label)
    parts.append(f"\u2192 {host}")
    return " ".join(parts)


def _outcome(events: list[PageEvent]) -> str:
    if not events or any(event.error for event in events) or not events[-1].executed:
        return "blocked"
    if len(events) >= DEFAULT_MAX_STEPS:
        return "steps-limit"
    return "done"


def render_workflow(events: Iterable[PageEvent]) -> str:
    """Render the Mermaid chart for a run. Pure function of the event list."""
    events = list(events)
    failing = [event for event in events if event.failing]
    lines = ["flowchart TD"]
    for event in events:
        lines.append(f'    S{event.step}["{_escape_mermaid(_event_label(event))}"]')
    counts = f"{len(events)} step" + ("s" if len(events) != 1 else "")
    if failing:
        counts += f", {len(failing)} failing"
    lines.append(f'    T(["{_escape_mermaid(f"{_outcome(events)} ({counts})")}"])')
    for first, second in zip(events, events[1:]):
        lines.append(f"    S{first.step} --> S{second.step}")
    if events:
        lines.append(f"    S{events[-1].step} --> T")
    for event in failing:
        lines.append(f"    class S{event.step} failing")
    if failing:
        lines.append("    classDef failing fill:#c0392b,color:#fff")
    return "\n".join(lines) + "\n"


def write_workflow(run_dir: Path | str, events: Iterable[PageEvent]) -> Path:
    path = Path(run_dir) / ARTIFACT_WORKFLOW
    _write_text(path, render_workflow(events))
    return path


# --- defects.csv ----------------------------------------------------------


def _defect_row(finding: Finding) -> list:
    return [
        finding.defect_id,
        finding.stage,
        finding.kind,
        finding.severity,
        finding.confidence,
        finding.status,
        finding.url,
        finding.action,
        finding.timestamp,
        finding.title,
        finding.detail,
        ";".join(finding.evidence_refs),
    ]


def write_defects(run_dir: Path | str, findings: Iterable[Finding]) -> Path:
    """Write defects.csv with the fixed DEFECT_COLUMNS header, sorted by (stage, defect_id)."""
    path = Path(run_dir) / ARTIFACT_DEFECTS
    rows = sorted(findings, key=lambda finding: (finding.stage, finding.defect_id))
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(DEFECT_COLUMNS)
        for finding in rows:
            writer.writerow(_defect_row(finding))
    return path


# --- run.json -------------------------------------------------------------


def playwright_stage_status(context: RunContext) -> str:
    if not context.config.playwright:
        return "skipped"
    return "failed-setup" if context.provenance.get("playwright_stage") == "failed-setup" else "on"


def vision_stage_status(context: RunContext) -> str:
    if context.config.vision_mode == "off":
        return "off"
    raw = context.provenance.get("vision_stage")
    if raw in ("declined", "skipped-no-model"):
        return raw
    if raw == "ran":
        count = sum(1 for finding in context.findings if finding.stage == "vision")
        return f"ran({count})"
    # Requested but no recorded status: nothing ran and nothing left the
    # machine, so record the conservative non-pass value.
    return "declined"


def stage_table(context: RunContext) -> dict[str, str]:
    return {"playwright": playwright_stage_status(context), "vision": vision_stage_status(context)}


def _whitelisted_provenance(provenance: dict) -> dict:
    kept = {}
    for key in PROVENANCE_TEXT_KEYS:
        value = provenance.get(key)
        if isinstance(value, str):
            kept[key] = value
    for key in PROVENANCE_INT_KEYS:
        value = provenance.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            kept[key] = value
    return kept


def _git_sha() -> str | None:
    try:
        done = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=_REPO_ROOT,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode == 0 and done.stdout.strip():
        return done.stdout.strip()
    return None


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _evidence_index(run_dir: Path) -> dict[str, str]:
    index = {}
    paths = sorted(p for p in run_dir.rglob("*") if p.is_file() and p.name != ARTIFACT_RUN)
    for path in paths:
        index[path.relative_to(run_dir).as_posix()] = _sha256_file(path)
    return index


def run_summary(context: RunContext, run_dir: Path | str) -> dict:
    """Build the run.json payload. Whitelist-only: no raw provenance dump."""
    run_dir = Path(run_dir)
    config = context.config
    provider = None if config.runner == RUNNER_LAYA else (config.provider or JEV_DEFAULT_PROVIDER)
    provenance = _whitelisted_provenance(context.provenance)
    findings = context.findings
    return {
        "run_id": context.run_id,
        "started": _iso_utc(context.started_at),
        "finished": _iso_utc(time.time()),
        "target_url": config.target_url,
        "runner": config.runner,
        "provider": provider,
        "decision": {"backend": provenance.get("backend"), "model": provenance.get("model")},
        "stages": stage_table(context),
        "steps": len(context.events),
        "findings": {
            "total": len(findings),
            "by_status": {status: sum(1 for f in findings if f.status == status) for status in FINDING_STATUSES},
            "by_kind": {kind: sum(1 for f in findings if f.kind == kind) for kind in FINDING_KINDS},
        },
        "renderer": {
            "version": MERMAID_VERSION,
            "sha256": MERMAID_SHA256,
            "url": RENDERER_URL,
            "source": RENDERER_SOURCE,
        },
        "tool": {"python": platform.python_version(), "package": PACKAGE_VERSION, "git": _git_sha()},
        "provenance": provenance,
        "evidence": _evidence_index(run_dir),
    }


def write_run(run_dir: Path | str, context: RunContext) -> Path:
    path = Path(run_dir) / ARTIFACT_RUN
    _write_json(path, run_summary(context, run_dir))
    return path
