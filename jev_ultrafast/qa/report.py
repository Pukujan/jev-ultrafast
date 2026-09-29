"""Offline report builder for one QA run.

build_report copies the bundled Mermaid renderer into the run folder and
writes report.html around it. The HTML never reaches for the network: the
renderer is a local file, the chart source is inlined, evidence images use
relative paths, and the provenance appendix comes from run.json, which is
whitelist-only. JUF-0003 / issue #9.
"""

from __future__ import annotations

import html
import json
import re
import shutil
import webbrowser
from pathlib import Path
from urllib.parse import quote, urlparse

from . import artifacts
from .contracts import (
    ARTIFACT_DEFECTS,
    ARTIFACT_RENDERER,
    ARTIFACT_REPORT,
    ARTIFACT_RUN,
    ARTIFACT_WORKFLOW,
    STATUS_CANDIDATE,
    STATUS_CONFIRMED,
    STATUS_UNVERIFIED,
    Finding,
    RunContext,
)

_ASSETS = Path(__file__).resolve().parent / "assets"
_INFO_NAME = "mermaid.INFO.txt"
_STEP_RE = re.compile(r"\bstep (\d+)")
_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg")

_PLAYWRIGHT_LINES = {
    "on": "playwright evidence recorded",
    "skipped": "playwright skipped for this run",
    "failed-setup": "playwright setup failed, so browser evidence is missing",
    "not-run": "the run stopped before the evidence stage",
}

_STYLE = """\
body { font-family: system-ui, sans-serif; max-width: 960px; margin: 2rem auto;
       padding: 0 1rem; line-height: 1.55; color: #1b1b1b; }
h1, h2, h3 { font-weight: 600; line-height: 1.25; }
.banner { font-size: 1.15rem; padding: 0.75rem 1rem; border: 1px solid #c9c9c9;
          border-radius: 6px; background: #fafafa; }
section.defect { border: 1px solid #dedede; border-radius: 6px;
                 padding: 0.5rem 1rem; margin: 1rem 0; }
img.thumb { max-width: 240px; max-height: 160px; border: 1px solid #ccc;
            margin: 0.25rem 0.5rem 0.25rem 0; }
code { background: #f2f2f2; padding: 0 0.25rem; border-radius: 3px; }
table { border-collapse: collapse; margin: 0.5rem 0 1.25rem; }
td, th { border: 1px solid #d8d8d8; padding: 0.25rem 0.5rem; text-align: left;
         font-size: 0.9rem; vertical-align: top; }
pre.csv { overflow-x: auto; font-size: 0.85rem; }
.failing-note { color: #c0392b; }
"""


def _banner(findings: list[Finding]) -> str:
    if not findings:
        return "no findings recorded"
    confirmed = sum(1 for f in findings if f.status == STATUS_CONFIRMED)
    candidate = sum(1 for f in findings if f.status == STATUS_CANDIDATE)
    unverified = sum(1 for f in findings if f.status == STATUS_UNVERIFIED)
    noun = "finding" if len(findings) == 1 else "findings"
    text = f"{len(findings)} {noun}: {confirmed} confirmed, {candidate} candidate"
    if unverified:
        text += f", {unverified} unverified"
    return text


def _vision_line(status: str, findings: list[Finding], provenance: dict) -> str:
    if status.startswith("ran"):
        count = sum(1 for f in findings if f.stage == "vision")
        detail = ""
        provider = provenance.get("vision_provider")
        model = provenance.get("vision_model")
        if isinstance(provider, str) and provider and isinstance(model, str) and model:
            detail = f" via {provider} {model}"
        elif isinstance(provider, str) and provider:
            detail = f" via {provider}"
        elif isinstance(model, str) and model:
            detail = f" via {model}"
        if count == 0:
            return f"vision ran{detail} and added no findings"
        noun = "finding" if count == 1 else "findings"
        return f"vision ran{detail} and added {count} {noun}"
    if status == "declined":
        return "vision was offered and declined"
    if status == "skipped-no-model":
        return "vision skipped: no local vision model installed"
    return "vision not run"


def _failing_links(context: RunContext) -> str:
    cited: dict[int, list[Finding]] = {}
    for finding in context.findings:
        match = _STEP_RE.search(finding.action)
        if match:
            cited.setdefault(int(match.group(1)), []).append(finding)
    parts = []
    for event in context.events:
        if not event.failing:
            continue
        refs = cited.get(event.step, [])
        if refs:
            links = ", ".join(
                f'<a href="#{html.escape(f.defect_id)}">{html.escape(f.defect_id)}</a>' for f in refs
            )
            parts.append(f"step {event.step} \u2192 {links}")
        else:
            parts.append(f"step {event.step}")
    return ", ".join(parts)


def _defect_section(finding: Finding) -> str:
    evidence_bits = []
    for ref in finding.evidence_refs:
        if ref.lower().endswith(_IMAGE_SUFFIXES):
            evidence_bits.append(f'<img class="thumb" src="{quote(ref)}" alt="{html.escape(ref)}">')
        else:
            evidence_bits.append(f"<code>{html.escape(ref)}</code>")
    lines = [
        f'<section class="defect" id="{html.escape(finding.defect_id)}">',
        f"<h3>{html.escape(finding.defect_id)}: {html.escape(finding.title)} "
        f"({html.escape(finding.severity)}, {html.escape(finding.status)})</h3>",
        f"<p>Kind {html.escape(finding.kind)}, observed by the {html.escape(finding.stage)} stage, "
        f"confidence {finding.confidence:g}.</p>",
    ]
    if finding.detail:
        lines.append(f"<p>{html.escape(finding.detail)}</p>")
    lines.append(f"<p>Reproduce on <code>{html.escape(finding.url)}</code>: {html.escape(finding.action)}.</p>")
    lines.append(f"<p>Recorded {html.escape(finding.timestamp)}.</p>")
    if evidence_bits:
        lines.append(f"<p>Evidence: {' '.join(evidence_bits)}</p>")
    lines.append("</section>")
    return "\n".join(lines)


def _table(rows: list[tuple[str, str]], header: tuple[str, str] | None = None) -> str:
    head = ""
    if header:
        head = f"<tr><th>{html.escape(header[0])}</th><th>{html.escape(header[1])}</th></tr>"
    body = "".join(f"<tr><td>{html.escape(str(a))}</td><td>{html.escape(str(b))}</td></tr>" for a, b in rows)
    return f"<table>{head}{body}</table>"


def _provenance_rows(run_info: dict) -> list[tuple[str, str]]:
    decision = run_info.get("decision") or {}
    tool = run_info.get("tool") or {}
    renderer = run_info.get("renderer") or {}
    stages = run_info.get("stages") or {}
    summary = run_info.get("findings") or {}
    by_status = summary.get("by_status") or {}
    status_bits = ", ".join(f"{count} {name}" for name, count in by_status.items() if count)
    total = summary.get("total", 0)
    rows = [
        ("run id", run_info.get("run_id") or "unknown"),
        ("started", run_info.get("started") or ""),
        ("finished", run_info.get("finished") or ""),
        ("target", run_info.get("target_url") or ""),
        ("runner", run_info.get("runner") or ""),
        ("provider", run_info.get("provider") or "none, local decision"),
        ("decision backend", decision.get("backend") or "not recorded"),
        ("decision model", decision.get("model") or "not recorded"),
        ("playwright stage", stages.get("playwright") or "not recorded"),
        ("vision stage", stages.get("vision") or "not recorded"),
        ("steps", str(run_info.get("steps", 0))),
        ("findings", f"{total}: {status_bits}" if total else "none"),
        ("renderer", f"mermaid {renderer.get('version')} (sha256 {renderer.get('sha256')})"),
        ("renderer source", renderer.get("source") or ""),
        ("python", tool.get("python") or ""),
        ("package", tool.get("package") or ""),
        ("git", tool.get("git") or "not recorded"),
    ]
    for key, value in (run_info.get("provenance") or {}).items():
        if key not in ("backend", "model"):
            rows.append((key, str(value)))
    return rows


def _render_html(context: RunContext, run_info: dict, mmd: str, csv_text: str) -> str:
    findings = context.findings
    banner = _banner(findings)
    host = urlparse(context.config.target_url).hostname or context.config.target_url
    stages = run_info.get("stages") or {}
    playwright_line = _PLAYWRIGHT_LINES.get(stages.get("playwright", ""), "playwright status unknown")
    vision_line = _vision_line(stages.get("vision", "off"), findings, run_info.get("provenance") or {})
    runner_line = f"Runner {run_info.get('runner') or context.config.runner}"
    if run_info.get("provider"):
        runner_line += f" with provider {run_info['provider']}"
    failing_links = _failing_links(context)
    if findings:
        sections = "\n".join(_defect_section(f) for f in findings)
    else:
        sections = "<p>No defects were recorded in this run.</p>"
    evidence_rows = sorted((run_info.get("evidence") or {}).items())

    parts = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        f"<title>Frontend QA report \u2014 {html.escape(host)}</title>",
        '<script src="mermaid.min.js"></script>',
        "<script>mermaid.initialize({startOnLoad:true});</script>",
        "<style>",
        _STYLE,
        "</style>",
        "</head>",
        "<body>",
        "<h1>Frontend QA report</h1>",
        f'<p class="banner"><strong>{html.escape(banner)}</strong></p>',
        f"<p>Target <code>{html.escape(context.config.target_url)}</code>. "
        f"{runner_line}. {playwright_line}; {vision_line}.</p>",
        "<h2>Workflow</h2>",
        "<p>The chart shows each decision step of the run in order. "
        "Red marks a step where a fault was observed.</p>",
        '<pre class="mermaid">',
        html.escape(mmd),
        "</pre>",
    ]
    if failing_links:
        parts.append(f'<p class="failing-note">Failing steps on the chart: {failing_links}.</p>')
    parts.append("<h2>Defects</h2>")
    parts.append(sections)
    if csv_text:
        parts.extend([
            "<details>",
            "<summary>defects.csv as written</summary>",
            f'<pre class="csv">{html.escape(csv_text)}</pre>',
            "</details>",
        ])
    parts.extend([
        "<h2>Provenance</h2>",
        _table(_provenance_rows(run_info)),
        "<h3>Evidence index</h3>",
        _table(evidence_rows, header=("file", "sha256")) if evidence_rows else "<p>No evidence files were written.</p>",
        "</body>",
        "</html>",
    ])
    return "\n".join(parts) + "\n"


def _reindex_run_evidence(run_dir: Path) -> None:
    """Re-hash the folder so run.json can vouch for report.html and the renderer copies."""
    run_path = run_dir / ARTIFACT_RUN
    if not run_path.exists():
        return
    run_info = json.loads(run_path.read_text(encoding="utf-8"))
    run_info["evidence"] = artifacts.evidence_index(run_dir)
    with open(run_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(run_info, handle, indent=2)
        handle.write("\n")


def build_report(run_dir: Path | str, context: RunContext) -> Path:
    """Copy the renderer, then write report.html from the run folder's artifacts."""
    run_dir = Path(run_dir)
    shutil.copyfile(_ASSETS / ARTIFACT_RENDERER, run_dir / ARTIFACT_RENDERER)
    shutil.copyfile(_ASSETS / _INFO_NAME, run_dir / _INFO_NAME)
    workflow_path = run_dir / ARTIFACT_WORKFLOW
    if workflow_path.exists():
        mmd = workflow_path.read_text(encoding="utf-8")
    else:
        mmd = artifacts.render_workflow(context.events, context.provenance.get("explorer_terminal"))
    run_path = run_dir / ARTIFACT_RUN
    if run_path.exists():
        run_info = json.loads(run_path.read_text(encoding="utf-8"))
    else:
        run_info = artifacts.run_summary(context, run_dir)
    csv_path = run_dir / ARTIFACT_DEFECTS
    csv_text = csv_path.read_text(encoding="utf-8") if csv_path.exists() else ""
    report_path = run_dir / ARTIFACT_REPORT
    with open(report_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(_render_html(context, run_info, mmd, csv_text))
    _reindex_run_evidence(run_dir)
    return report_path


def open_report(run_dir: Path | str):
    """Open the saved report in the default browser via a file:// URI."""
    return webbrowser.open((Path(run_dir) / ARTIFACT_REPORT).resolve().as_uri())
