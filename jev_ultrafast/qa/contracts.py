"""Shared vocabulary for the frontend QA harness.

Types and constants live here; behaviour lives in the stage modules.
Every QA module imports this file; this file imports none of them.
JUF-0003 / issue #9.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

# Runner selection is provider selection. Blank picks laya; laya never
# touches the network for decisions and needs no keys.
RUNNER_LAYA = "laya"
RUNNER_JEV = "jev"
RUNNERS = (RUNNER_LAYA, RUNNER_JEV)

PROVIDER_OPENROUTER = "openrouter"
PROVIDER_TYPESAFE = "typesafe"
PROVIDER_OPENCODE = "opencode"
PROVIDER_OPENJEV = "openjev"
PROVIDER_VISION = "vision"
JEV_PROVIDERS = (PROVIDER_OPENROUTER, PROVIDER_TYPESAFE, PROVIDER_OPENCODE, PROVIDER_OPENJEV)
JEV_DEFAULT_PROVIDER = PROVIDER_OPENROUTER
# Arms whose decision model runs on this machine: no credential, loopback only.
# openjev is an APUS-OpenJev GGUF served by a local Ollama.
LOCAL_JEV_PROVIDERS = (PROVIDER_OPENJEV,)

# Local Laya runtime: ChenneyZhuang/laya-browser-agent, `localdecide serve`,
# binding 127.0.0.1. Discovery is healthz-first; missing runtime fails closed.
LAYA_BASE_URL_ENV = "LAYA_BASE_URL"
LAYA_DEFAULT_BASE_URL = "http://127.0.0.1:8791"
LAYA_HEALTH_PATH = "/healthz"
LAYA_MODELS_PATH = "/v1/models"
LAYA_SYSTEMONE_PATH = "/v1/systemone"

# Supported provider variable names, per arm. Discovery scans names and
# prefixes only, never values.
PROVIDER_ENV_ALIASES: dict[str, tuple[str, ...]] = {
    PROVIDER_OPENROUTER: (
        "OPENROUTER_API_KEY",
        "OPENROUTER_DECISIONS_URL",
        "OPENROUTER_MODEL",
        "TEXT_MODEL_API_KEY",
        "TEXT_MODEL_BASE_URL",
        "TEXT_MODEL",
    ),
    PROVIDER_TYPESAFE: ("TYPESAFE_API_KEY", "TYPESAFE_SYSTEMONE_URL", "TYPESAFE_MODEL"),
    PROVIDER_OPENCODE: ("OPENCODE_API_KEY", "OPENCODE_BASE_URL"),
    # Local arm: endpoint and model names only; it has no credential by design.
    PROVIDER_OPENJEV: ("OPENJEV_OLLAMA_URL", "OPENJEV_MODEL"),
    # Vision stays separate from the Jev decision credential (issue #9).
    PROVIDER_VISION: (
        "VISION_API_KEY",
        "VISION_BASE_URL",
        "VISION_MODEL",
        "VISION_OLLAMA_URL",
    ),
}

SEVERITIES = ("P0", "P1", "P2", "P3")
FINDING_KINDS = ("broken_link", "dead_control", "browser_error", "layout", "visual")
FINDING_STAGES = ("explorer", "playwright", "vision")
STATUS_CANDIDATE = "candidate"
STATUS_CONFIRMED = "confirmed"
STATUS_UNVERIFIED = "unverified"
FINDING_STATUSES = (STATUS_CANDIDATE, STATUS_CONFIRMED, STATUS_UNVERIFIED)

# Contract names fixed by issue #9; evidence basenames follow the
# human-output-naming legend at .content-system/filename-legends/frontend-qa.md
ARTIFACT_DEFECTS = "defects.csv"
ARTIFACT_WORKFLOW = "workflow.mmd"
ARTIFACT_RUN = "run.json"
ARTIFACT_REPORT = "report.html"
ARTIFACT_EVENTS = "events.json"
ARTIFACT_EVIDENCE = "evidence"
ARTIFACT_RENDERER = "mermaid.min.js"
DEFECT_COLUMNS = (
    "defect_id", "stage", "kind", "severity", "confidence", "status",
    "url", "action", "timestamp", "title", "detail", "evidence_refs",
)

ALLOWED_TARGET_SCHEMES = ("http", "https")  # hosted or localhost; never file paths or repos
IDLE_KEY_TTL_SECONDS = 3 * 60 * 60  # CLI-entered keys expire after idle time, default yes
KEYWATCH_STATE = "keywatch.json"  # watchdog recovery state, under the ignored qa-runs root
DEFAULT_MAX_STEPS = 60

MERMAID_VERSION = "11.17.2"
MERMAID_SHA256 = "581ed7d74bd9048d0e3a91363927d72ef22942d7722546b27f7cc29e35390eb8"


@dataclass(slots=True)
class Finding:
    """One reported frontend fault.

    A model claim alone never passes: without deterministic corroboration the
    status stays candidate.
    """

    defect_id: str
    stage: str
    kind: str
    severity: str
    title: str
    url: str
    action: str  # reproducible step, e.g. 'step 7: CLICK [12] "Sign in"'
    timestamp: str  # ISO-8601 UTC
    detail: str = ""
    confidence: float = 0.0
    status: str = STATUS_CANDIDATE
    evidence_refs: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PageEvent:
    """One observed decision and execution cycle; the Mermaid chart's only input."""

    step: int
    timestamp_ms: int
    url: str
    title: str
    operation: str
    target: str | None
    label: str
    action_id: str
    executed: bool
    page_changed: bool
    error: str | None = None
    fingerprint: str = ""
    runner: str = RUNNER_LAYA
    confidence: float | None = None
    failing: bool = False  # set when this step is the observed failure point


class Decider(Protocol):
    """Guided-exploration backend; state/goal/history like model.choose()."""

    name: str

    def decide(self, state: dict, goal: str, history: list[dict]) -> dict:
        """Return the choose()-shaped dict: operation, target, choice, confidence."""


class Transport(Protocol):
    """Provider-neutral Decisions transport.

    prepare() may rewrite the request body for the provider dialect (Laya
    flattens dict criteria to compact strings). request() returns the raw
    provider answer dict. Local transports carry no auth.
    """

    name: str
    model_slug: str

    def prepare(self, body: dict) -> dict: ...

    def request(self, body: dict) -> dict: ...


class Stage(Protocol):
    """An optional evidence stage (Playwright or vision)."""

    name: str

    def run(self, context: RunContext) -> None: ...


@dataclass(slots=True)
class RunConfig:
    target_url: str
    runner: str = RUNNER_LAYA
    provider: str | None = None  # meaningful only when runner == jev; then default openrouter
    goals: tuple[str, ...] = (
        "Explore the page the way a first-time visitor would. "
        "Report anything broken: dead controls, failed links, console errors, layout faults.",
    )
    playwright: bool = True  # default on, independently skippable
    vision_mode: str = "off"  # off|ollama|openrouter; never an automatic pass
    vision_model: str | None = None
    vision_confirmed: bool = False  # images leave the device only after explicit yes
    max_steps: int = DEFAULT_MAX_STEPS
    out_root: str = "qa-runs"
    idle_cleanup: bool = True
    noninteractive: bool = False


@dataclass(slots=True)
class RunContext:
    config: RunConfig
    run_id: str
    run_dir: str
    started_at: float
    events: list[PageEvent] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)

    def add_finding(self, **data: Any) -> Finding:
        data.setdefault("defect_id", f"D{len(self.findings) + 1:03d}")
        finding = Finding(**data)
        self.findings.append(finding)
        return finding

    def add_event(self, event: PageEvent) -> None:
        self.events.append(event)
