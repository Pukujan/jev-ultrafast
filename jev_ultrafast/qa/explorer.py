"""Guided exploration loop: observe, decide, execute one observed target, watch for faults.

The explorer reuses the agent's action space and execution boundary: a decider may
only name an operation plus an id that came from the observed snapshot, and only
such ids reach the browser. Findings recorded here stay candidates; deterministic
stages corroborate them. The explorer never claims an HTTP status.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from ..browser import Browser, StalePage
from ..model import action_space
from .contracts import RUNNER_LAYA, STATUS_CANDIDATE, PageEvent

_TITLE_ERROR_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"\b404\b",
        r"\bnot found\b",
        r"\b500\b",
        r"\binternal server error\b",
        r"\bserver error\b",
        r"\b502\b",
        r"\bbad gateway\b",
        r"\b503\b",
        r"\bservice unavailable\b",
    )
)
# Body copy mentions "500" and "not found" on healthy pages; only compound
# error phrases are specific enough to come from page text.
_TEXT_ERROR_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"\bpage not found\b",
        r"\bfile not found\b",
        r"\berror code:\s*404\b",
        r"\binternal server error\b",
        r"\bserver error\b",
        r"\bbad gateway\b",
        r"\bservice unavailable\b",
    )
)

_SEVERITY = {"dead_control": "P2", "broken_link": "P1", "browser_error": "P1"}
_TITLE = {
    "dead_control": "A click changed nothing",
    "broken_link": "Navigation landed on an error page",
    "browser_error": "The browser reported an error",
}


def _now_ms():
    return int(time.time() * 1000)


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _label(action):
    return action["label"].split(" → ")[0]


def _action_text(step, operation, target, label):
    index = f" [{target}]" if target else ""
    return f'step {step}: {operation}{index} "{label}"'


def _looks_like_error_page(page):
    title = page.get("title", "").lower()
    text = page.get("text", "").lower()
    return any(p.search(title) for p in _TITLE_ERROR_PATTERNS) or any(
        p.search(text) for p in _TEXT_ERROR_PATTERNS
    )


SETTLE_POLL_SECONDS = 0.5
SETTLE_MAX_SECONDS = 10.0
MAX_STALE_RECOVERIES = 3


def _has_substance(page):
    """True when the snapshot offers real controls or visible text, not just scroll/wait."""
    kinds = {action.get("kind") for action in page.get("actions") or []}
    return bool(kinds & {"click", "fill", "select"}) or bool((page.get("text") or "").strip())


def _settle(observe, sleep=None, monotonic=None):
    """Observe until the page has substance or the deadline passes.

    Client-rendered sites report document-complete while the app bundle is
    still mounting: the first snapshot then holds zero controls, and a
    decision model handed an empty page answers DONE or BLOCKED correctly.
    defect. Returns (page, polls); the caller records whether the page ever
    gained controls, and the walk continues either way so a genuinely
    control-free site still produces evidence instead of a blocked run.
    """
    sleep = sleep or time.sleep
    monotonic = monotonic or time.monotonic
    deadline = monotonic() + SETTLE_MAX_SECONDS
    polls = 0
    while True:
        try:
            page = observe()
        except Exception:
            # A snapshot that fails mid-mount is the same race in a different
            # costume: keep polling, and only surface the error if the whole
            # budget expires without a usable page.
            if monotonic() >= deadline:
                raise
            sleep(SETTLE_POLL_SECONDS)
            continue
        polls += 1
        if _has_substance(page) or monotonic() >= deadline:
            return page, polls
        sleep(SETTLE_POLL_SECONDS)


class Explorer:
    """Observe, decide, execute, re-observe; append one PageEvent per cycle."""

    def __init__(self, config, context, browser_factory=None, decider=None):
        if decider is None:
            # Runner selection is provider selection: no silent default decider,
            # never a fallback from laya to a network arm.
            raise ValueError("explorer needs an explicit decider")
        self.config = config
        self.context = context
        self.browser_factory = browser_factory or Browser
        self.decider = decider

    def run(self):
        config = self.config
        goal = "\n".join(config.goals) if isinstance(config.goals, (list, tuple)) else str(config.goals)
        seen = set()

        def record(kind, url, action, detail, confidence):
            # Dedupe on the reproducible action, independent of its step number.
            key = (kind, url, re.sub(r"^step \d+:\s*", "", action))
            if key in seen:
                return None
            seen.add(key)
            return self.context.add_finding(
                stage="explorer",
                kind=kind,
                severity=_SEVERITY[kind],
                title=_TITLE[kind],
                url=url,
                action=action,
                timestamp=_now_iso(),
                detail=detail,
                confidence=confidence or 0.0,
                status=STATUS_CANDIDATE,
            )

        terminal = "browser_error"
        try:
            browser = self.browser_factory(config.target_url)
        except Exception as exc:
            # A target that never opened is a setup failure, not a site defect:
            # no finding, so the CLI fails closed with exit 2.
            self.context.provenance["explorer_open_error"] = f"{type(exc).__name__}: {exc}"[:200]
            self._finish("browser_error")
            return "browser_error"
        try:
            try:
                page, polls = _settle(lambda: browser.observe(screenshot=False))
                gained = "settled" if _has_substance(page) else "no substance"
                self.context.provenance["explorer_settle"] = f"{gained} after {polls} polls"
            except Exception as exc:
                self.context.provenance["explorer_open_error"] = f"{type(exc).__name__}: {exc}"[:200]
                terminal = "browser_error"
            else:
                terminal = self._walk(browser, page, goal, record)
        finally:
            try:
                browser.close()
            except Exception:
                pass
        self._finish(terminal)
        return terminal

    def _walk(self, browser, page, goal, record):
        config, context = self.config, self.context
        history = []
        pending = None
        stale = 0
        step = 0
        while True:
            _elements, targets, _controls = action_space(page["actions"])
            try:
                decision = self.decider.decide(page, goal, history)
            except StopIteration as exc:
                self._log_decision(step, page, targets, error=f"StopIteration: {exc}")
                return "decider_exhausted"
            except (KeyError, ValueError) as exc:
                # A decider that cannot answer its own snapshot is exhausted, not
                # a browser fault: stop cleanly without inventing a finding.
                self._log_decision(step, page, targets, error=f"{type(exc).__name__}: {exc}")
                return "decider_exhausted"
            if not isinstance(decision, dict):
                self._log_decision(step, page, targets, error=f"non-dict decision: {decision!r}")
                return "decider_exhausted"
            self._log_decision(step, page, targets, decision=decision)
            operation = decision.get("operation")
            if operation in {"DONE", "BLOCKED"}:
                return operation.lower()
            if not operation:
                return "decider_exhausted"

            choice = decision.get("choice")
            target = decision.get("target")
            action = next((a for a in page["actions"] if a["id"] == choice), None)
            if action is None and target is not None and operation in targets and target in targets[operation]:
                action = targets[operation][target]
            if action is None:
                # The decider named something the snapshot never offered: out of bounds.
                step += 1
                context.add_event(
                    PageEvent(
                        step=step,
                        timestamp_ms=_now_ms(),
                        url=page["url"],
                        title=page.get("title", ""),
                        operation=operation,
                        target=target,
                        label=str(choice),
                        action_id=str(choice),
                        executed=False,
                        page_changed=False,
                        fingerprint=page.get("fingerprint", ""),
                        runner=config.runner,
                        confidence=decision.get("confidence"),
                        error="choice is not an observed action id",
                    )
                )
                return "decider_exhausted"

            step += 1
            label = _label(action)
            action_text = _action_text(step, operation, target, label)
            confidence = decision.get("confidence")
            text = decision.get("text") or ""
            try:
                browser.act(action, page, text=text or None)
            except StalePage:
                # The page moved between the snapshot and this action. That is
                # the harness's own race against a still-mounting site, not a
                # fault in the target: re-observe and keep walking. Nothing
                # executed, so no event and no finding; the marker line tells a
                # reader why the same step number is judged twice. The bounded
                # counter stops a permanently flickering page.
                self._log_decision(step, page, targets, error="stale snapshot")
                stale += 1
                context.provenance["explorer_stale_retries"] = stale
                step -= 1  # nothing executed, so this attempt costs no step
                if stale > MAX_STALE_RECOVERIES:
                    context.provenance["explorer_settle"] = f"stale after {stale} recoveries"
                    return "stale_page"
                page, _ = _settle(lambda: browser.observe(screenshot=False))
                continue
            except Exception as exc:
                event = PageEvent(
                    step=step,
                    timestamp_ms=_now_ms(),
                    url=page["url"],
                    title=page.get("title", ""),
                    operation=operation,
                    target=target,
                    label=label,
                    action_id=action["id"],
                    executed=False,
                    page_changed=False,
                    fingerprint=page.get("fingerprint", ""),
                    runner=config.runner,
                    confidence=confidence,
                    error=f"{type(exc).__name__}: {exc}",
                )
                context.add_event(event)
                finding = record(
                    "browser_error",
                    page["url"],
                    action_text,
                    f"Executing {action_text} raised {type(exc).__name__}: {exc}",
                    confidence,
                )
                if finding is not None:
                    event.failing = True
                return "browser_error"
            stale = 0
            try:
                fresh = browser.observe(screenshot=False)
            except Exception as exc:
                event = PageEvent(
                    step=step,
                    timestamp_ms=_now_ms(),
                    url=page["url"],
                    title=page.get("title", ""),
                    operation=operation,
                    target=target,
                    label=label,
                    action_id=action["id"],
                    executed=True,
                    page_changed=False,
                    fingerprint=page.get("fingerprint", ""),
                    runner=config.runner,
                    confidence=confidence,
                    error=f"re-observe failed: {type(exc).__name__}: {exc}",
                )
                context.add_event(event)
                finding = record(
                    "browser_error",
                    page["url"],
                    action_text,
                    f"Observing after {action_text} raised {type(exc).__name__}: {exc}",
                    confidence,
                )
                if finding is not None:
                    event.failing = True
                return "browser_error"

            changed = fresh["fingerprint"] != page["fingerprint"]
            event = PageEvent(
                step=step,
                timestamp_ms=_now_ms(),
                url=fresh["url"],
                title=fresh.get("title", ""),
                operation=operation,
                target=target,
                label=label,
                action_id=action["id"],
                executed=True,
                page_changed=changed,
                fingerprint=fresh["fingerprint"],
                runner=config.runner,
                confidence=confidence,
            )
            context.add_event(event)
            history.append(
                {
                    "step": step,
                    "action": label,
                    "kind": action["kind"],
                    "choice": action["id"],
                    "operation": operation,
                    "target": target,
                    "text": text or None,
                    "page_changed": changed,
                    "url": fresh["url"],
                }
            )

            if fresh["url"] != page["url"] and _looks_like_error_page(fresh):
                finding = record(
                    "broken_link",
                    fresh["url"],
                    action_text,
                    f'Navigating landed on "{fresh.get("title", "")}" at {fresh["url"]}. '
                    "The explorer cannot see HTTP status; the Playwright stage corroborates.",
                    confidence,
                )
                if finding is not None:
                    event.failing = True

            if action["kind"] == "click" and pending is None:
                pending = {
                    "event": event,
                    "action": action_text,
                    "url": page["url"],
                    "fingerprint": page["fingerprint"],
                    "count": 0,
                }
            if pending is not None:
                if fresh["fingerprint"] == pending["fingerprint"]:
                    pending["count"] += 1
                    if pending["count"] >= 2:
                        finding = record(
                            "dead_control",
                            pending["url"],
                            pending["action"],
                            f"The page was unchanged on two consecutive observations after {pending['action']}.",
                            confidence,
                        )
                        if finding is not None:
                            pending["event"].failing = True
                        pending = None
                else:
                    pending = None

            if step >= config.max_steps:
                return "max_steps"
            if not _has_substance(fresh):
                # The dead-control and error-page checks above compared the raw
                # snapshot; only the next decision must not see a page that is
                # still mounting after this action.
                fresh, _ = _settle(lambda: browser.observe(screenshot=False))
            page = fresh

    def _log_decision(self, step, page, targets, decision=None, error=None):
        """Append one judgment to decisions.jsonl before its action is observed.

        PageEvents record what happened to the browser; this record is the
        model's own answer — which candidates it saw, what it picked, how sure
        it was — so a zero-step run says why it stopped instead of going
        silent. No page text: labels, counts, and the chosen ids only.
        """
        record = {
            "step": step + 1,
            "url": page.get("url"),
            "runner": self.config.runner,
            "candidates": {operation: len(ids) for operation, ids in (targets or {}).items()},
        }
        if error is not None:
            record["error"] = error[:200]
        if decision is not None:
            for key in ("operation", "target", "choice", "confidence"):
                record[key] = decision.get(key)
        try:
            path = Path(self.context.run_dir) / "decisions.jsonl"
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
        except OSError:
            pass  # diagnostics never break a walk

    def _finish(self, terminal):
        self.context.provenance["explorer_terminal"] = terminal
        if self.config.runner == RUNNER_LAYA:
            self.context.provenance["laya_criteria_flattening"] = "describe-v1"
