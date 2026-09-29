"""Local Laya runtime adapter: discovery, fail-closed check, and the transport.

The runtime is `localdecide serve` from https://github.com/ChenneyZhuang/laya-browser-agent
bound to loopback. The wire format is the one `jev_ultrafast.model` already builds;
only the criteria values are flattened to Laya's own describe-style prompt form.
No auth, no keys, and no decision request ever leaves the machine.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

import httpx

from .. import model
from . import contracts

INSTALL_STEPS = (
    "Install and start the local runtime first:\n"
    "  git clone https://github.com/ChenneyZhuang/laya-browser-agent\n"
    "  cd laya-browser-agent && pip install -e '.[mlx]'   # Apple Silicon, or '.[torch]'\n"
    "  localdecide serve\n"
    "Then rerun jev-qa. The Laya path never falls back to Jev."
)

_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


class LayaUnavailable(RuntimeError):
    """The local decision runtime is missing or unhealthy. Nothing executed."""


def base_url(override: str | None = None) -> str:
    url = override or os.environ.get(contracts.LAYA_BASE_URL_ENV) or contracts.LAYA_DEFAULT_BASE_URL
    url = url.rstrip("/")
    host = urlparse(url).hostname or ""
    if host not in _LOOPBACK:
        raise LayaUnavailable(
            f"Laya is loopback-only; refusing base {url!r} because host {host!r} is not local.\n{INSTALL_STEPS}"
        )
    return url


def discover(base_url_: str | None = None) -> dict:
    """Probe healthz/models on the local runtime; fail closed with install steps."""
    url = base_url(base_url_)
    try:
        health = httpx.get(url + contracts.LAYA_HEALTH_PATH, timeout=3)
        health.raise_for_status()
        info = health.json()
    except Exception as error:
        raise LayaUnavailable(
            f"No healthy Laya runtime at {url} ({type(error).__name__}).\n{INSTALL_STEPS}"
        ) from None
    if not info.get("ok"):
        raise LayaUnavailable(f"Laya healthz answered but is not ready at {url}: {info}\n{INSTALL_STEPS}")
    models: list[str] = []
    try:
        listing = httpx.get(url + contracts.LAYA_MODELS_PATH, timeout=3).json()
        models = [m.get("name", "") for m in listing.get("models", [])]
    except Exception:
        pass  # models listing is best-effort; healthz already proved the runtime
    return {
        "base_url": url,
        "backend": info.get("backend", ""),
        "max_options_per_question": info.get("max_options_per_question"),
        "models": models,
    }


def _describe(index: str, value: dict) -> str:
    """One option line, matching localdecide Element.describe() shape (describe-v1).

    The dict criteria from build_request_body carry the label inside
    `element: "[3] Where to?"`; role/value/flags come from the other keys.
    """
    element = str(value.get("element", f"[{index}]"))
    head, _, rest = element.partition("] ")
    label = (rest or element)[:60]
    text = f"[{index}] {label}"
    if value.get("role"):
        text += f" ({value['role']})"
    current = value.get("current_value", "")
    if current:
        text += f" = {str(current)[:30]!r}"
    for name in ("checked", "selected", "expanded"):
        if value.get(name) is not None:
            text += f" {name}={str(value[name]).lower()}"
    return text


def flatten(body: dict) -> dict:
    """Rewrite dict criteria to describe-v1 lines; leave string options untouched.

    Keys are preserved, so response validation and target mapping are unchanged.
    """
    flattened = dict(body)
    questions = {}
    for name, question in body.get("questions", {}).items():
        question = dict(question)
        criteria = question.get("criteria")
        if isinstance(criteria, dict):
            question["criteria"] = {
                index: _describe(index, value) if isinstance(value, dict) else value
                for index, value in criteria.items()
            }
        questions[name] = question
    flattened["questions"] = questions
    return flattened


class LayaTransport:
    """contracts.Transport for the local runtime: prepared body, no Authorization."""

    name = "laya"
    model_slug = "localdecide"

    def __init__(self, base: str | None = None):
        self.base = base_url(base)

    def prepare(self, body: dict) -> dict:
        return flatten(body)

    def request(self, body: dict) -> dict:
        try:
            response = httpx.post(self.base + contracts.LAYA_SYSTEMONE_PATH, json=body, timeout=60)
        except httpx.HTTPError as error:
            raise LayaUnavailable(
                f"Laya request failed at {self.base} ({type(error).__name__}); nothing executed."
            ) from error
        if response.is_error:
            raise LayaUnavailable(
                f"Laya returned HTTP {response.status_code}: {response.text[:200]}; nothing executed."
            )
        return response.json()


class LayaDecider:
    """Decider-shaped wrapper so the explorer runs identically on either runner."""

    name = "laya"

    def __init__(self, transport: LayaTransport | None = None):
        self.transport = transport or LayaTransport()

    def decide(self, state: dict, goal: str, history: list[dict]) -> dict:
        return model.decide(self.transport, state, goal, history)

def laya_decider(base_url_: str | None = None) -> LayaDecider:
    return LayaDecider(LayaTransport(base_url_))


