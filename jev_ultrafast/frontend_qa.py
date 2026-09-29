"""One-command, evidence-first frontend checks and portable run artifacts."""

from __future__ import annotations

import argparse
import csv
import difflib
import getpass
import hashlib
import html
import importlib.metadata
import json
import os
import platform
import re
import subprocess
import sys
import time
import webbrowser
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from jev_ultrafast.providers import LayaAdapter, select_runner

PROVIDERS = {
    "openrouter": ("OPENROUTER_API_KEY", "OPENROUTER_API_URL", "OPENROUTER_MODEL"),
    "typesafe": ("TYPESAFE_API_KEY", "TYPESAFE_API_URL", "TYPESAFE_MODEL"),
    "opencode": ("OPENCODE_API_KEY", "OPENCODE_API_URL", "OPENCODE_MODEL"),
}
ALIASES = {
    "openrouter": ("OPENROUTER", "OPEN_ROUTER"),
    "typesafe": ("TYPESAFE", "TYPE_SAFE"),
    "opencode": ("OPENCODE", "OPEN_CODE"),
}


def discover_key_names(env_file: Path, provider: str) -> list[tuple[str, str]]:
    """Return candidate variable names and safe prefixes; never return secret values."""
    if not env_file.exists():
        return []
    names = []
    aliases = ALIASES[provider]
    for line in env_file.read_text(encoding="utf-8").splitlines():
        match = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$", line)
        if not match:
            continue
        name, value = match.groups()
        score = max(difflib.SequenceMatcher(None, name.upper(), alias + "_API_KEY").ratio() for alias in aliases)
        if "KEY" in name.upper() and score >= 0.66 and value:
            names.append((name, value[:4]))
    return sorted(names, key=lambda item: item[0])


def read_env_value(env_file: Path, name: str) -> str | None:
    """Read the selected value after confirmation; callers must never render it."""
    if not env_file.exists():
        return None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        match = re.match(rf"\s*{re.escape(name)}\s*=\s*(.*?)\s*$", line)
        if match:
            return match.group(1).strip("'\"")
    return None


def record_cli_key(record_path: Path, env_file: Path, name: str, value: str, *, enabled: bool, now: float) -> bool:
    """Remember only a digest for a key entered by this invocation."""
    if not enabled:
        return False
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(
        json.dumps(
            {
                "env_file": str(env_file),
                "name": name,
                "sha256": hashlib.sha256(value.encode()).hexdigest(),
                "last_used": now,
            }
        ),
        encoding="utf-8",
    )
    return True


def remove_exact_env_key(env_file: Path, name: str, digest: str) -> bool:
    """Remove one CLI-owned key only if its current value matches its private digest."""
    if not env_file.exists():
        return False
    lines = env_file.read_text(encoding="utf-8").splitlines(keepends=True)
    kept, removed = [], False
    for line in lines:
        match = re.match(rf"\s*{re.escape(name)}\s*=\s*(.*?)\s*(?:\r?\n)?$", line)
        value = match.group(1).strip("'\"") if match else None
        if not removed and value is not None and hashlib.sha256(value.encode()).hexdigest() == digest:
            removed = True
        else:
            kept.append(line)
    if removed:
        env_file.write_text("".join(kept), encoding="utf-8")
    return removed


def cleanup_watch(record_path: Path, *, clock=time.time, sleep=time.sleep) -> None:
    """Resumable idle watcher; only private metadata and a digest are persisted."""
    try:
        while record_path.exists():
            record = json.loads(record_path.read_text(encoding="utf-8"))
            remaining = float(record["last_used"]) + 3 * 60 * 60 - clock()
            if remaining <= 0:
                break
            sleep(min(60, remaining))
        remove_exact_env_key(Path(record["env_file"]), record["name"], record["sha256"])
    finally:
        record_path.unlink(missing_ok=True)


def start_cleanup_watch(record_path: Path) -> None:
    """Launch or recover the detached idle watcher for a CLI-owned key."""
    if record_path.exists():
        record = json.loads(record_path.read_text(encoding="utf-8"))
        watcher_pid = record.get("watcher_pid")
        if watcher_pid:
            try:
                os.kill(int(watcher_pid), 0)
                return
            except OSError:
                pass
        process = subprocess.Popen(
            [sys.executable, "-m", "jev_ultrafast.frontend_qa", "--cleanup-watch"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        record["watcher_pid"] = process.pid
        record_path.write_text(json.dumps(record), encoding="utf-8")


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[dict] = []
        self.controls: list[dict] = []
        self._active = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a" and a.get("href"):
            self._active = {"href": a["href"], "text": "", "target": a.get("target", "")}
            self.links.append(self._active)
        if tag in {"button", "input", "select", "textarea"}:
            self.controls.append({"tag": tag, **a})

    def handle_data(self, data):
        if self._active is not None:
            self._active["text"] += data.strip()

    def handle_endtag(self, tag):
        if tag == "a":
            self._active = None


@dataclass
class Finding:
    id: str
    severity: str
    confidence: float
    kind: str
    title: str
    url: str
    action: str
    timestamp: str
    evidence: str


def inspect_url(url: str) -> tuple[list[Finding], list[dict]]:
    stamp = datetime.now(timezone.utc).isoformat()
    events = [{"type": "navigate", "url": url, "timestamp": stamp}]
    findings = []
    try:
        request = Request(url, headers={"User-Agent": "Jev-Frontend-QA/0.1"})
        with urlopen(request, timeout=20) as response:
            body = response.read(2_000_000).decode("utf-8", "replace")
            status = response.status
            mime = response.headers.get("content-type", "")
    except Exception as exc:
        return [
            Finding(
                "F1",
                "P1",
                1.0,
                "navigation",
                "Page could not be loaded",
                url,
                "Open the URL",
                stamp,
                type(exc).__name__,
            )
        ], events
    events.append(
        {"type": "response", "url": url, "status": status, "timestamp": datetime.now(timezone.utc).isoformat()}
    )
    if status >= 400:
        findings.append(
            Finding(
                "F1", "P1", 1.0, "http", f"Page returned HTTP {status}", url, "Open the URL", stamp, f"HTTP {status}"
            )
        )
    parser = Page()
    if "html" in mime:
        parser.feed(body)
        for link in parser.links:
            href = link["href"].strip()
            if href.startswith(("#", "mailto:", "tel:", "javascript:")):
                if href.startswith("javascript:"):
                    findings.append(
                        Finding(
                            f"F{len(findings) + 1}",
                            "P2",
                            0.75,
                            "link",
                            "Script URL used as link",
                            url,
                            f"Follow {href[:80]}",
                            stamp,
                            "Observed anchor href",
                        )
                    )
                continue
            target = urljoin(url, href)
            if urlparse(target).scheme not in {"http", "https"}:
                continue
            try:
                req = Request(target, method="HEAD", headers={"User-Agent": "Jev-Frontend-QA/0.1"})
                with urlopen(req, timeout=10) as response:
                    code = response.status
            except Exception as exc:
                code = getattr(exc, "code", 0) or 0
            events.append(
                {
                    "type": "link_check",
                    "url": target,
                    "status": code,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            if code >= 400 or code == 0:
                findings.append(
                    Finding(
                        f"F{len(findings) + 1}",
                        "P1",
                        0.95,
                        "broken_link",
                        "Link did not return a page",
                        url,
                        f"Follow link {href}",
                        stamp,
                        f"{target} returned {code or 'connection error'}",
                    )
                )
        for c in parser.controls:
            if c["tag"] == "button" and "disabled" not in c and not c.get("onclick"):
                # HTML alone cannot establish JS-bound listeners; this is a review lead, not a dead-control verdict.
                events.append(
                    {
                        "type": "control_observed",
                        "tag": c["tag"],
                        "label": c.get("aria-label", c.get("id", "unlabeled")),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
    return findings, events


def inspect_browser(url: str, out: Path) -> tuple[list[Finding], list[dict]]:
    """Optional Playwright pass: browser errors and viewport overflow, no model judge."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return [], [
            {
                "type": "playwright_skipped",
                "reason": "install jev-ultrafast[qa]",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ]
    stamp = datetime.now(timezone.utc).isoformat()
    events = []
    findings = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.on(
                "pageerror",
                lambda error: events.append(
                    {
                        "type": "browser_error",
                        "message": str(error)[:300],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                ),
            )
            page.on(
                "console",
                lambda msg: (
                    events.append(
                        {
                            "type": "console_error",
                            "message": msg.text[:300],
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                    if msg.type == "error"
                    else None
                ),
            )
            response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(500)
            browser_event = {
                "type": "browser_loaded",
                "url": page.url,
                "status": response.status if response else None,
                "timestamp": stamp,
            }
            events.insert(0, browser_event)
            page.screenshot(path=str(out / "viewport.png"), full_page=True)
            metrics = page.evaluate("""() => ({width: document.documentElement.scrollWidth, viewport: innerWidth,
                height: document.documentElement.scrollHeight, viewportHeight: innerHeight,
                disabled: [...document.querySelectorAll('button:disabled,[aria-disabled=true]')].map(x =>
                  x.getAttribute('aria-label') || x.innerText || x.tagName)})""")
            if metrics["width"] > metrics["viewport"] + 2:
                findings.append(
                    Finding(
                        "B1",
                        "P2",
                        0.85,
                        "layout_overflow",
                        "Page extends beyond the viewport",
                        page.url,
                        "Load at 1280px viewport",
                        stamp,
                        f"width={metrics['width']}, viewport={metrics['viewport']}; evidence=viewport.png",
                    )
                )
            for index, message in enumerate([e for e in events if e["type"] in {"browser_error", "console_error"}], 1):
                findings.append(
                    Finding(
                        f"B{index + 1}",
                        "P1",
                        0.9,
                        "browser_error",
                        "Browser reported a JavaScript error",
                        page.url,
                        "Load the page",
                        stamp,
                        f"{message['type']}: {message['message']}",
                    )
                )
            browser.close()
    except Exception as exc:
        events.append({"type": "playwright_unavailable", "reason": type(exc).__name__, "timestamp": stamp})
    return findings, events


def source_revision() -> str | None:
    """Identify the checked-out Jev source revision without reading target metadata."""
    root = Path(__file__).resolve().parent.parent
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            check=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def source_dirty() -> bool | None:
    root = Path(__file__).resolve().parent.parent
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            capture_output=True,
            check=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return bool(result.stdout.strip())


def tool_version() -> str:
    try:
        return importlib.metadata.version("jev-ultrafast")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def write_artifacts(
    out: Path, target: str, events: list[dict], findings: list[Finding], provider: str, runner: str = "jev"
):
    out.mkdir(parents=True, exist_ok=True)
    with (out / "defects.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=list(asdict(findings[0]).keys()) if findings else list(Finding.__annotations__)
        )
        writer.writeheader()
        writer.writerows(asdict(x) for x in findings)
    lines = ["flowchart TD", "  N0[Start frontend check]"]
    previous = "N0"
    for i, event in enumerate(events, 1):
        node = f"N{i}"
        label = (
            html.escape(f"{event['type']} {event.get('status', '')} {event.get('url', '')[:45]}", quote=False)
            .replace("[", "(")
            .replace("]", ")")
        )
        lines += [f"  {node}[{label}]"]
        lines += [f"  {previous} --> {node}"]
        previous = node
    for i, finding in enumerate(findings, 1):
        lines += [f"  F{i}[FAIL {finding.id}: {finding.title}]"]
        lines += [f"  {previous} -.-> F{i}"]
    (out / "workflow.mmd").write_text("\n".join(lines) + "\n", encoding="utf-8")
    run = {
        "run_id": out.name,
        "target": target,
        "runner": runner,
        "provider": provider,
        "stages": {
            "static_http": "completed",
            "playwright": (
                "completed"
                if any(event.get("type") == "browser_loaded" for event in events)
                else "unavailable"
                if any(event.get("type") == "playwright_unavailable" for event in events)
                else "NOT RUN"
            ),
            "vision": "NOT RUN",
        },
        "environment": {
            "tool_version": tool_version(),
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "source_revision": source_revision(),
        "source_dirty": source_dirty(),
        "started_at": events[0]["timestamp"],
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "events": events,
        "findings": [asdict(x) for x in findings],
        "limitations": [
            "Static HTML checks do not execute page JavaScript; browser errors, interaction outcomes, "
            "and viewport layout require a browser-backed pass."
        ],
    }
    (out / "run.json").write_text(json.dumps(run, indent=2), encoding="utf-8")
    rows = "".join(
        f"<li id='{html.escape(x.id)}'><h3>{html.escape(x.severity)} {html.escape(x.title)}</h3>"
        f"<p>{html.escape(x.url)}<br>{html.escape(x.action)}<br>{html.escape(x.evidence)}</p></li>"
        for x in findings
    )
    # The inline SVG is the offline rendering of the same captured-event flow.
    chart_nodes = []
    for i, event in enumerate(events):
        y = 30 + i * 58
        label = html.escape(f"{event['type']} {event.get('status', '')} {event.get('url', '')[:75]}")
        chart_nodes.append(
            f"<g transform='translate(30,{y})'><rect width='720' height='42' rx='6' fill='#e8eef8' stroke='#778'/>"
            f"<text x='12' y='26'>{label}</text></g>"
        )
        if i:
            chart_nodes.append(f"<path d='M390 {y - 16} V{y}' stroke='#778' marker-end='url(#arrow)'/>")
    for i, finding in enumerate(findings):
        y = 50 + (len(events) + i) * 58
        title = html.escape(f"FAIL {finding.id}: {finding.title}")
        chart_nodes.append(
            f"<path d='M390 {max(60, (len(events) - 1) * 58 + 60)} V{y}' stroke='#b42318' stroke-dasharray='5 4'/>"
        )
        chart_nodes.append(
            f"<a href='#{html.escape(finding.id)}'><g transform='translate(30,{y})'>"
            f"<rect width='720' height='42' rx='6' fill='#fee2e2' stroke='#b42318'/>"
            f"<text x='12' y='26'>{title}</text></g></a>"
        )
    height = max(100, 70 + (len(events) + len(findings)) * 58)
    report = f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width">
<title>Frontend QA report</title>
<style>
body {{ font: 16px system-ui; max-width: 1000px; margin: 2rem auto; padding: 0 1rem; color: #17212b }}
li {{ padding: 1rem; border-bottom: 1px solid #ddd }}
svg {{ width: 100%; height: auto }}
text {{ font: 14px system-ui }}
</style>
<body>
<h1>Frontend QA report</h1>
<p>Target: <a href="{html.escape(target)}">{html.escape(target)}</a> · provider: {html.escape(provider)}</p>
<p>{len(findings)} finding(s). An empty list is not a browser interaction pass. Vision: NOT RUN.</p>
<h2>Observed flow</h2>
<svg viewBox="0 0 780 {height}" role="img" aria-label="Observed browser event flow">
<defs>
<marker id="arrow" markerWidth="8" markerHeight="8" refX="4" refY="4">
<path d="M0 0 L8 4 L0 8" fill="#778"/>
</marker>
</defs>
{"".join(chart_nodes)}</svg>
<h2>Findings</h2><ul>{rows or "<li>No defects observed by the static checks.</li>"}</ul>
<h2>Limitations</h2>
<p>Interaction outcomes and visual judgment were not measured by the static pass. See run.json for stage status.</p>
</body></html>"""
    (out / "report.html").write_text(report, encoding="utf-8")


def main():
    p = argparse.ArgumentParser(description="Run a frontend check and save a portable evidence report")
    p.add_argument("--url")
    p.add_argument("--runner", choices=("laya", "jev"))
    p.add_argument(
        "--provider",
        choices=tuple(PROVIDERS),
        help="Jev provider; only used when Jev is explicitly selected",
    )
    p.add_argument("--output", type=Path, default=Path("artifacts/frontend-qa"))
    p.add_argument("--no-playwright", action="store_true", help="Skip the default browser pass")
    p.add_argument("--vision", action="store_true", help="Request an optional visual judge (not configured yet)")
    p.add_argument("--cleanup-watch", action="store_true", help=argparse.SUPPRESS)
    args = p.parse_args()
    if args.cleanup_watch:
        cleanup_watch(Path.home() / ".jev-ultrafast" / "key-cleanup.json")
        return
    start_cleanup_watch(Path.home() / ".jev-ultrafast" / "key-cleanup.json")
    if args.vision:
        raise SystemExit("Vision is a separate optional stage; no judge adapter is configured in this release.")
    url = args.url or input("Target URL (hosted or already-running localhost URL): ").strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SystemExit("Enter a reachable HTTP(S) URL. Start any local app yourself, then provide its localhost URL.")
    runner = select_runner(args.runner or input("Exploration runner [Laya default / Jev comparison]: ").strip())
    if runner == "laya":
        try:
            LayaAdapter()
        except RuntimeError as exc:
            raise SystemExit(f"{exc} No Jev or deterministic-only fallback was used.") from exc
        raise SystemExit(
            "Laya is installed, but its Playwright exploration loop is not wired into this release. "
            "No deterministic-only pass or Jev fallback was used."
        )
    else:
        provider = args.provider or "openrouter"
        env_path = Path(__file__).resolve().parent.parent / ".env"
        candidates = discover_key_names(env_path, provider)
        selected = None
        if candidates:
            print("Candidate credentials (name and first four characters only):")
            for i, (name, prefix) in enumerate(candidates, 1):
                print(f" {i}. {name} ({prefix}…)")
            answer = input("Use candidate number, or enter a new key: ").strip()
            if answer.isdigit() and 1 <= int(answer) <= len(candidates):
                selected = candidates[int(answer) - 1][0]
        if selected is None:
            key = getpass.getpass(f"{provider} API key: ")
            if not key:
                raise SystemExit("A credential is required for the selected Jev provider.")
            env_path.parent.mkdir(parents=True, exist_ok=True)
            env_path.open("a", encoding="utf-8").write(f"\n{PROVIDERS[provider][0]}={key}\n")
            selected = PROVIDERS[provider][0]
            print("Remove this CLI-entered key after three idle hours? [Y/n]", end=" ", flush=True)
            cleanup = input().strip().lower() != "n"
            expiry = Path.home() / ".jev-ultrafast" / "key-cleanup.json"
            record_cli_key(expiry, env_path, selected, key, enabled=cleanup, now=time.time())
        os.environ[PROVIDERS[provider][0]] = key if "key" in locals() else read_env_value(env_path, selected) or ""
    out = args.output / datetime.now().strftime("%Y%m%d-%H%M%S")
    findings, events = inspect_url(url)
    if not args.no_playwright:
        browser_findings, browser_events = inspect_browser(url, out)
        findings.extend(browser_findings)
        events.extend(browser_events)
    write_artifacts(out, url, events, findings, provider if runner == "jev" else "laya", runner)
    webbrowser.open((out / "report.html").resolve().as_uri())
    expiry_path = Path.home() / ".jev-ultrafast" / "key-cleanup.json"
    if expiry_path.exists():
        record = json.loads(expiry_path.read_text(encoding="utf-8"))
        record["last_used"] = time.time()
        expiry_path.write_text(json.dumps(record), encoding="utf-8")
        start_cleanup_watch(expiry_path)
    print(f"Report saved to {out.resolve() / 'report.html'} ({len(findings)} finding(s))")


if __name__ == "__main__":
    main()
