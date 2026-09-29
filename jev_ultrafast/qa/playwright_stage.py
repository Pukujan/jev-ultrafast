"""Deterministic Playwright evidence stage for QA runs.

The stage revisits the URLs the exploration recorded, measures each page
with fixed settings, and reports what it can prove: link statuses, page
and console errors, layout overflow. It does not explore and does not
decide. Playwright is imported lazily inside run(); a missing browser
binary becomes a failed-setup provenance entry, never an exception, and
the run keeps its explorer evidence.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from jev_ultrafast.qa import contracts

VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 720
MAX_VISITED_URLS = 12
MAX_LINK_PROBES = 120
GOTO_TIMEOUT_MS = 30_000
LINK_TIMEOUT_MS = 10_000
MAX_CONSOLE_IN_RECORD = 20

# In-page probes. Named constants so fake pages in tests can dispatch on
# the exact expressions the stage evaluates.
NAV_TIMING_JS = """() => {
  try {
    const entries = performance.getEntriesByType('navigation');
    if (entries && entries.length > 0) {
      const t = entries[0];
      return {navigation_start: t.startTime, load_event_end: t.loadEventEnd,
              load_ms: Math.max(0, t.loadEventEnd - t.startTime)};
    }
    const t = performance.timing;
    return {navigation_start: t.navigationStart, load_event_end: t.loadEventEnd,
            load_ms: Math.max(0, t.loadEventEnd - t.navigationStart)};
  } catch (err) {
    return null;
  }
}"""

LINKS_JS = "() => Array.from(document.querySelectorAll('a[href]')).map((a) => a.href)"

LAYOUT_JS = """() => {
  const vw = window.innerWidth;
  const out = [];
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.width <= 0 && r.height <= 0) continue;
    const viewportOverflow = r.right > vw + 1 || r.left < -1;
    const scrollOverflow = el.scrollWidth - el.clientWidth > 1;
    if (!viewportOverflow && !scrollOverflow) continue;
    out.push({
      tag: el.tagName.toLowerCase(),
      id: el.id || null,
      classes: Array.from(el.classList).slice(0, 4),
      text: (el.textContent || '').trim().slice(0, 80),
      bbox: {x: Math.round(r.x), y: Math.round(r.y),
             width: Math.round(r.width), height: Math.round(r.height),
             scroll_width: el.scrollWidth, client_width: el.clientWidth},
      reason: viewportOverflow ? 'viewport' : 'scroll',
    });
    if (out.length >= 25) break;
  }
  return out;
}"""

CONFIRMED_LINK_STATUSES = (404, 410)
CANDIDATE_LINK_STATUSES = (401, 403, 405, 429)
BOT_CHALLENGE_MARKERS = (
    "cf-chl", "challenge-platform", "cf-browser-verification", "just a moment",
    "attention required", "verify you are human", "are you a robot", "ddos-guard",
)
ERROR_PAGE_MARKERS = (
    "page not found", "404 not found", "file not found", "is no longer available", "error 404",
)


def classify_link(status: int, body: str) -> tuple[str, str]:
    """Map one GET probe to a verdict: ok, candidate, or confirmed.

    Confirmed broken needs a hard signal: 404/410, a browser-visible error
    page, or a network-level failure (handled by the caller). Auth walls,
    rate limits, and bot challenges stay candidate with the status as
    evidence, because working links answer that way too.
    """
    text = (body or "").lower()
    if status in CONFIRMED_LINK_STATUSES:
        return contracts.STATUS_CONFIRMED, f"HTTP {status}"
    if status in CANDIDATE_LINK_STATUSES:
        return contracts.STATUS_CANDIDATE, f"HTTP {status}"
    if any(marker in text for marker in BOT_CHALLENGE_MARKERS):
        return contracts.STATUS_CANDIDATE, "bot challenge body"
    if status >= 500:
        return contracts.STATUS_CANDIDATE, f"HTTP {status}"
    if status < 400 and any(marker in text for marker in ERROR_PAGE_MARKERS):
        return contracts.STATUS_CONFIRMED, "error page body"
    if status >= 400:
        return contracts.STATUS_CANDIDATE, f"HTTP {status}"
    return "ok", f"HTTP {status}"


def speakable_phrase(title: str, fallback: str = "untitled page") -> str:
    """Turn a page title into a plain filename phrase per the legend."""
    words = [w for w in re.sub(r"[^0-9a-z]+", " ", (title or "").lower()).split()][:6]
    return " ".join(words) or fallback


def visited_urls(events: list[contracts.PageEvent], target_url: str | None = None,
                 limit: int = MAX_VISITED_URLS) -> list[str]:
    """Visited URLs: the entry page seeds first, then the exploration's, deduped and capped."""
    ordered: list[str] = []
    seen: set[str] = set()
    if target_url:
        ordered.append(target_url)
        seen.add(target_url)
    for event in events:
        if event.url and event.url not in seen:
            seen.add(event.url)
            ordered.append(event.url)
    return ordered[:limit]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _probe_one(request_context, href: str, source_url: str) -> dict:
    """One GET through the shared request context. Never a bare HEAD."""
    entry = {"href": href, "source_url": source_url, "status": None, "error": None,
             "verdict": None, "reason": "", "elapsed_ms": 0.0, "bytes": 0}
    started = time.perf_counter()
    try:
        response = request_context.get(href, timeout=LINK_TIMEOUT_MS)
        body = response.text()
        entry["status"] = response.status
        entry["bytes"] = len(body or "")
        entry["verdict"], entry["reason"] = classify_link(response.status, body or "")
    except Exception as exc:  # DNS failure or refused connection: confirmed broken
        entry["error"] = str(exc)
        entry["verdict"], entry["reason"] = contracts.STATUS_CONFIRMED, f"request failed: {exc}"
    entry["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 1)
    return entry


def _element_name(item: dict) -> str:
    name = str(item.get("tag") or "element")
    if item.get("id"):
        name += f"#{item['id']}"
    elif item.get("classes"):
        name += "." + ".".join(str(c) for c in item["classes"][:2])
    return name


def _layout_detail(item: dict) -> str:
    bbox = item.get("bbox") or {}
    parts = [
        f"reason={item.get('reason', 'overflow')}",
        f"bbox=({bbox.get('x')},{bbox.get('y')} {bbox.get('width')}x{bbox.get('height')})",
        f"scroll_width={bbox.get('scroll_width')} client_width={bbox.get('client_width')}",
    ]
    text = (item.get("text") or "").strip()
    if text:
        parts.append(f"text='{text[:60]}'")
    return " ".join(parts)


class PlaywrightStage:
    """Browser evidence sweep over the exploration's visited pages.

    Implements contracts.Stage. Playwright is imported inside run(), so
    this module loads on machines without browsers and tests can swap in
    fakes through playwright.sync_api.sync_playwright.
    """

    name = "playwright"

    def __init__(self, tracing: bool = False) -> None:
        self.tracing = tracing

    def run(self, context: contracts.RunContext) -> None:
        if not context.config.playwright:
            return  # skipped-by-config provenance is written by the CLI
        try:
            self._sweep(context)
        except Exception as exc:  # fail closed: record it, add nothing, never raise
            context.provenance["playwright_stage"] = "failed-setup"
            context.provenance["playwright_error"] = str(exc)

    def _sweep(self, context: contracts.RunContext) -> None:
        urls = visited_urls(context.events, context.config.target_url)
        step_by_url: dict[str, int] = {}
        for event in context.events:
            step_by_url.setdefault(event.url, event.step)
        evidence_dir = os.path.join(context.run_dir, contracts.ARTIFACT_EVIDENCE)
        os.makedirs(evidence_dir, exist_ok=True)

        from playwright.sync_api import sync_playwright  # lazy by design

        playwright = sync_playwright().start()
        browser = None
        try:
            browser = playwright.chromium.launch(headless=True)
            browser_context = browser.new_context(viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT})
            tracing_started = False
            try:
                if self.tracing:
                    browser_context.tracing.start(screenshots=True, snapshots=True)
                    tracing_started = True
                pages = [self._visit_page(browser_context, url, step_by_url.get(url, 0)) for url in urls]
                link_entries, capped = self._probe_links(browser_context.request, pages)
            finally:
                if tracing_started:
                    browser_context.tracing.stop(path=os.path.join(evidence_dir, "trace.zip"))
                browser_context.close()
        finally:
            if browser is not None:
                browser.close()
            playwright.stop()
        self._commit(context, urls, pages, link_entries, capped)

    def _visit_page(self, browser_context, url: str, step: int) -> dict:
        record = {"url": url, "step": step, "title": "", "status": None,
                  "navigation_ms": None, "load_ms": None, "screenshot_ms": None,
                  "console": [], "page_errors": [], "error": None,
                  "links": [], "layout": [], "_png": None}
        console: list[str] = []
        page_errors: list[str] = []
        page = browser_context.new_page()
        page.on("console", lambda msg: console.append(f"{msg.type}: {msg.text}"))
        page.on("pageerror", lambda err: page_errors.append(str(err)))
        try:
            started = time.perf_counter()
            response = page.goto(url, wait_until="load", timeout=GOTO_TIMEOUT_MS)
            record["navigation_ms"] = round((time.perf_counter() - started) * 1000, 1)
            record["status"] = response.status if response is not None else None
            timing = page.evaluate(NAV_TIMING_JS)
            if isinstance(timing, dict):
                record["load_ms"] = timing.get("load_ms")
            record["title"] = page.title or ""
            shot_started = time.perf_counter()
            record["_png"] = page.screenshot()
            record["screenshot_ms"] = round((time.perf_counter() - shot_started) * 1000, 1)
            record["links"] = [href for href in page.evaluate(LINKS_JS) or [] if isinstance(href, str)]
            layout = page.evaluate(LAYOUT_JS)
            record["layout"] = layout if isinstance(layout, list) else []
        except Exception as exc:
            record["error"] = str(exc)
        finally:
            record["console"] = console[:MAX_CONSOLE_IN_RECORD]
            record["page_errors"] = page_errors[:MAX_CONSOLE_IN_RECORD]
            page.close()
        return record

    def _probe_links(self, request_context, pages: list[dict]) -> tuple[list[dict], bool]:
        entries: list[dict] = []
        probed: set[str] = set()
        capped = False
        for record in pages:
            source = record["url"]
            for href in record["links"]:
                if len(entries) >= MAX_LINK_PROBES:
                    capped = True
                    break
                absolute = urljoin(source, href)
                parsed = urlparse(absolute)
                if parsed.scheme not in ("http", "https") or not parsed.hostname:
                    continue
                bare = absolute.split("#", 1)[0]
                if bare in probed or bare == source.split("#", 1)[0]:
                    continue
                probed.add(bare)
                entries.append(_probe_one(request_context, bare, source))
            if capped:
                break
        return entries, capped

    def _commit(self, context: contracts.RunContext, urls: list[str], pages: list[dict],
                link_entries: list[dict], capped: bool) -> None:
        evidence_dir = os.path.join(context.run_dir, contracts.ARTIFACT_EVIDENCE)
        os.makedirs(evidence_dir, exist_ok=True)
        seen_keys = {(f.kind, f.url, f.action) for f in context.findings}

        def add(**data):
            key = (data["kind"], data["url"], data["action"])
            if key in seen_keys:
                return None
            seen_keys.add(key)
            return context.add_finding(**data)

        clean_pages = []
        for record in pages:
            shot_rel = None
            if record["_png"] is not None:
                basename = f"step {record['step']:02d} {speakable_phrase(record['title'])}.png"
                with open(os.path.join(evidence_dir, basename), "wb") as fh:
                    fh.write(record["_png"])
                shot_rel = f"{contracts.ARTIFACT_EVIDENCE}/{basename}"
            refs = [shot_rel] if shot_rel else []
            action = f"playwright: open {record['url']}"
            if record["page_errors"]:
                title = ("uncaught page error" if len(record["page_errors"]) == 1
                         else f"{len(record['page_errors'])} uncaught page errors")
                add(stage=self.name, kind="browser_error", severity="P2", status=contracts.STATUS_CONFIRMED,
                    title=title, url=record["url"], action=f"{action} (pageerror)", timestamp=_now_iso(),
                    detail=" | ".join(t[:200] for t in record["page_errors"][:5])[:500], confidence=0.9,
                    evidence_refs=list(refs))
            console_errors = [m for m in record["console"] if m.startswith("error:")]
            if console_errors:
                title = "console error" if len(console_errors) == 1 else f"{len(console_errors)} console errors"
                add(stage=self.name, kind="browser_error", severity="P2", status=contracts.STATUS_CANDIDATE,
                    title=title, url=record["url"], action=f"{action} (console)", timestamp=_now_iso(),
                    detail=" | ".join(t[:200] for t in console_errors[:5])[:500], confidence=0.6,
                    evidence_refs=list(refs))
            for item in record["layout"]:
                name = _element_name(item)
                bbox = item.get("bbox") or {}
                signature = f"{name} at {bbox.get('x')},{bbox.get('y')} {bbox.get('width')}x{bbox.get('height')}"
                add(stage=self.name, kind="layout", severity="P2", status=contracts.STATUS_CONFIRMED,
                    title=f"layout overflow: {name}", url=record["url"],
                    action=f"{action} (layout {signature})",
                    timestamp=_now_iso(), detail=_layout_detail(item), confidence=0.9, evidence_refs=list(refs))
            clean = {k: v for k, v in record.items() if k not in ("_png", "links", "layout")}
            clean["screenshot"] = shot_rel
            clean["console_count"] = len(record["console"])
            clean["links_found"] = len(record["links"])
            clean_pages.append(clean)

        confirmed_links = candidate_links = 0
        for index, entry in enumerate(link_entries, start=1):
            host = re.sub(r"[^0-9a-z.-]", "_", (urlparse(entry["href"]).hostname or "unknown-host").lower())
            basename = f"link {index:02d} {host}.json"
            rel = f"{contracts.ARTIFACT_EVIDENCE}/{basename}"
            with open(os.path.join(evidence_dir, basename), "w", encoding="utf-8") as fh:
                json.dump(entry, fh, indent=2, sort_keys=True)
            if entry["verdict"] == "ok":
                continue
            if entry["verdict"] == contracts.STATUS_CONFIRMED:
                confirmed_links += 1
                title, confidence = f"broken link: {entry['reason']}", 1.0
            else:
                candidate_links += 1
                title, confidence = f"possible broken link: {entry['reason']}", 0.6
            add(stage=self.name, kind="broken_link", severity="P2", status=entry["verdict"], title=title,
                url=entry["href"], action=f"playwright: GET {entry['href']}", timestamp=_now_iso(),
                detail=f"linked from {entry['source_url']}", confidence=confidence, evidence_refs=[rel])

        self._corroborate_dead_controls(context, set(urls))

        context.provenance["playwright_stage"] = "on"
        context.provenance["playwright_viewport"] = {"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT}
        context.provenance["tracing_mode"] = "on" if self.tracing else "off"
        context.provenance["playwright_pages"] = clean_pages
        context.provenance["playwright_links"] = {
            "probed": len(link_entries), "confirmed": confirmed_links,
            "candidate": candidate_links, "capped": capped,
        }

    def _corroborate_dead_controls(self, context: contracts.RunContext, visited: set[str]) -> None:
        """Upgrade explorer dead-control candidates this stage revisited.

        Same URL plus a matching control label confirms the candidate; a
        confirmed dead interactive control is severity P1.
        """
        labels_by_url: dict[str, set[str]] = {}
        for event in context.events:
            if event.label:
                labels_by_url.setdefault(event.url, set()).add(event.label)
        for finding in context.findings:
            if finding.kind != "dead_control" or finding.stage != "explorer":
                continue
            if finding.status == contracts.STATUS_CONFIRMED or finding.url not in visited:
                continue
            haystack = f"{finding.action} {finding.title}"
            labels = labels_by_url.get(finding.url, ())
            if not any(label in haystack for label in labels):
                continue
            finding.status = contracts.STATUS_CONFIRMED
            finding.severity = "P1"
            finding.confidence = max(finding.confidence, 0.9)
