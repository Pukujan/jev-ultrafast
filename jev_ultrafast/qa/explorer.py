"""Guided exploration loop: observe, decide, execute one observed target, watch for faults.

The explorer reuses the agent's action space and execution boundary: a decider may
only name an operation plus an id that came from the observed snapshot, and only
such ids reach the browser. Findings recorded here stay candidates; deterministic
stages corroborate them. The explorer never claims an HTTP status.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone

from ..browser import Browser
from ..model import action_space
from .contracts import RUNNER_LAYA, STATUS_CANDIDATE, PageEvent

_ERROR_PAGE_PATTERNS = tuple(
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
    content = f'{page.get("title", "")}\n{page.get("text", "")}'.lower()
    return any(pattern.search(content) for pattern in _ERROR_PAGE_PATTERNS)


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
            record(
                "browser_error",
                config.target_url,
                "open target",
                f"Opening {config.target_url} failed: {type(exc).__name__}: {exc}",
                0.0,
            )
            self._finish("browser_error")
            return "browser_error"
        try:
            try:
                page = browser.observe(screenshot=False)
            except Exception as exc:
                record(
                    "browser_error",
                    config.target_url,
                    "open target",
                    f"Opening {config.target_url} failed: {type(exc).__name__}: {exc}",
                    0.0,
                )
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
        step = 0
        while True:
            _elements, targets, _controls = action_space(page["actions"])
            try:
                decision = self.decider.decide(page, goal, history)
            except StopIteration:
                return "decider_exhausted"
            except (KeyError, ValueError):
                # A decider that cannot answer its own snapshot is exhausted, not
                # a browser fault: stop cleanly without inventing a finding.
                return "decider_exhausted"
            if not isinstance(decision, dict):
                return "decider_exhausted"
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
            except Exception as exc:
                context.add_event(
                    PageEvent(
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
                )
                record(
                    "browser_error",
                    page["url"],
                    action_text,
                    f"Executing {action_text} raised {type(exc).__name__}: {exc}",
                    confidence,
                )
                return "browser_error"
            try:
                fresh = browser.observe(screenshot=False)
            except Exception as exc:
                context.add_event(
                    PageEvent(
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
                )
                record(
                    "browser_error",
                    page["url"],
                    action_text,
                    f"Observing after {action_text} raised {type(exc).__name__}: {exc}",
                    confidence,
                )
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
                record(
                    "broken_link",
                    fresh["url"],
                    action_text,
                    f'Navigating landed on "{fresh.get("title", "")}" at {fresh["url"]}. '
                    "The explorer cannot see HTTP status; the Playwright stage corroborates.",
                    confidence,
                )

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
            page = fresh

    def _finish(self, terminal):
        self.context.provenance["explorer_terminal"] = terminal
        if self.config.runner == RUNNER_LAYA:
            self.context.provenance["laya_criteria_flattening"] = "describe-v1"
