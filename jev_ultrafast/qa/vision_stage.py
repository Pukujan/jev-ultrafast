"""Optional vision review stage for QA runs.

Vision is opt-in and default off. When armed it reviews the Playwright
stage's screenshots with an image-capable model and records what the
model points out as candidate findings: vision verdicts never confirm a
defect on their own, and a skipped vision stage is never a pass.

Providers:

- ollama: probes a local Ollama (VISION_OLLAMA_URL, default loopback
  11434) for installed image-capable models and uses one of them. This
  stage never pulls or downloads a model, and local review sends no
  screenshot off the device.
- openrouter: hosted review behind an explicit confirmation. Credentials
  come strictly from VISION_API_KEY / VISION_BASE_URL / VISION_MODEL.

A vision key or URL never appears in provenance; only the model string
does. All HTTP goes through one httpx client, injectable for offline
tests.
"""

from __future__ import annotations

import base64
import os
import re
from datetime import datetime, timezone

import httpx

from jev_ultrafast.qa import contracts

VISION_API_KEY_ENV = "VISION_API_KEY"
VISION_BASE_URL_ENV = "VISION_BASE_URL"
VISION_MODEL_ENV = "VISION_MODEL"
VISION_OLLAMA_URL_ENV = "VISION_OLLAMA_URL"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_HOSTED_VISION_URL = "https://openrouter.ai/api/v1"
TAGS_TIMEOUT_S = 5.0
REVIEW_TIMEOUT_S = 120.0
MAX_SCREENSHOTS = 5
TWO_BILLION_GUARD = 2.5  # default pick stays in the 2B class; larger picks must already be installed

# Installed Ollama model families known to accept images.
VISION_MODEL_FAMILIES = (
    "llava", "bakllava", "moondream", "minicpm-v", "llama3.2-vision",
    "llama4", "qwen2-vl", "qwen2.5-vl", "qwen3-vl", "gemma3", "granite-vision",
    "aya-vision", "smolvlm", "internvl", "glm-4.5v", "kimi-vl",
)

CLEAN_ANSWERS = {"", "no", "no defects", "clean", "ok", "n/a", "nothing", "looks fine"}

REVIEW_PROMPT = (
    "You are reviewing one screenshot of a web page from a QA run. "
    "Describe any visual defects you can see: clipping, overflow, misalignment, "
    "broken spacing, or overlapping elements. Name the region each defect appears in. "
    "If the page looks correct, answer with the single word: none"
)


def _vision_capable(name: str) -> bool:
    lowered = name.lower()
    return any(family in lowered for family in VISION_MODEL_FAMILIES)


def _params_billions(model: dict) -> float:
    """Best-effort parameter count: declared size first, then Q4 estimate."""
    declared = str(((model.get("details") or {}).get("parameter_size") or "")).strip().lower()
    match = re.match(r"([0-9]+(?:\.[0-9]+)?)\s*b", declared)
    if match:
        return float(match.group(1))
    size_bytes = model.get("size") or 0
    return size_bytes / 5e8 if size_bytes else 999.0  # roughly 4 bits per parameter


def _looks_clean(answer: str) -> bool:
    text = (answer or "").strip().lower().rstrip(".!:")
    return text in CLEAN_ANSWERS or text.startswith("none")


def _screenshot_step(basename: str) -> int | None:
    match = re.match(r"step (\d+) .+\.png$", basename)
    return int(match.group(1)) if match else None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class VisionStage:
    """Screenshot review stage. Implements contracts.Stage."""

    name = "vision"

    def __init__(self, client: httpx.Client | None = None) -> None:
        # Injectable client keeps unit tests offline; a real run builds one.
        self._client = client

    def run(self, context: contracts.RunContext) -> None:
        mode = context.config.vision_mode
        if mode not in ("ollama", "openrouter"):
            return  # off or unknown: the CLI records the skip, never this stage
        client = self._client or httpx.Client(timeout=REVIEW_TIMEOUT_S)
        try:
            if mode == "ollama":
                self._run_ollama(context, client)
            else:
                self._run_openrouter(context, client)
        finally:
            if self._client is None:
                client.close()

    def _run_ollama(self, context: contracts.RunContext, client: httpx.Client) -> None:
        base_url = os.environ.get(VISION_OLLAMA_URL_ENV, DEFAULT_OLLAMA_URL).rstrip("/")
        try:
            models = self._installed_models(client, base_url)
        except Exception as exc:
            self._skip(context, f"ollama unreachable: {exc}")
            return
        candidates = [m for m in models if _vision_capable(str(m.get("name", "")))]
        context.provenance["vision_candidates"] = [str(m.get("name", "")) for m in candidates]
        if not candidates:
            context.provenance["vision_stage"] = "skipped-no-model"
            context.provenance["vision_reason"] = "no local vision model installed; skipped"
            return
        model = self._choose_ollama_model(context, candidates)
        if model is None:
            return
        model_name = str(model.get("name", ""))

        def review(png_bytes: bytes) -> str:
            payload = {
                "model": model_name,
                "stream": False,
                "messages": [{"role": "user", "content": REVIEW_PROMPT,
                              "images": [base64.b64encode(png_bytes).decode("ascii")]}],
            }
            response = client.post(f"{base_url}/api/chat", json=payload, timeout=REVIEW_TIMEOUT_S)
            response.raise_for_status()
            return str((response.json().get("message") or {}).get("content") or "")

        self._review(context, model_name=model_name, provider="ollama", review=review)

    def _installed_models(self, client: httpx.Client, base_url: str) -> list[dict]:
        response = client.get(f"{base_url}/api/tags", timeout=TAGS_TIMEOUT_S)
        response.raise_for_status()
        models = response.json().get("models", [])
        return models if isinstance(models, list) else []

    def _choose_ollama_model(self, context: contracts.RunContext, candidates: list[dict]) -> dict | None:
        wanted = context.config.vision_model
        if wanted:
            for model in candidates:
                name = str(model.get("name", ""))
                if name == wanted or name.split(":", 1)[0] == wanted:
                    return model
            self._skip(context, f"requested vision model {wanted} is not installed; skipped")
            return None
        ranked = sorted(candidates, key=lambda m: (_params_billions(m), int(m.get("size") or 0)))
        within_guard = [m for m in ranked if _params_billions(m) <= TWO_BILLION_GUARD]
        return (within_guard or ranked)[0]

    def _run_openrouter(self, context: contracts.RunContext, client: httpx.Client) -> None:
        if not context.config.vision_confirmed:
            context.provenance["vision_stage"] = "declined"
            context.provenance["vision_reason"] = "screenshots leave the device only after an explicit yes"
            return
        api_key = os.environ.get(VISION_API_KEY_ENV, "").strip()
        model = (os.environ.get(VISION_MODEL_ENV) or context.config.vision_model or "").strip()
        if not api_key or not model:
            self._skip(context, "VISION_API_KEY or VISION_MODEL missing; skipped")
            return
        base_url = os.environ.get(VISION_BASE_URL_ENV, DEFAULT_HOSTED_VISION_URL).rstrip("/")

        def review(png_bytes: bytes) -> str:
            body = {"model": model, "messages": [{"role": "user", "content": [
                {"type": "text", "text": REVIEW_PROMPT},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/png;base64,{base64.b64encode(png_bytes).decode('ascii')}"}},
            ]}]}
            headers = {"Authorization": f"Bearer {api_key}"}
            response = client.post(f"{base_url}/chat/completions", json=body, headers=headers,
                                   timeout=REVIEW_TIMEOUT_S)
            response.raise_for_status()
            choices = response.json().get("choices") or []
            if not choices:
                return ""
            return str((choices[0].get("message") or {}).get("content") or "")

        self._review(context, model_name=model, provider="openrouter", review=review)

    def _skip(self, context: contracts.RunContext, reason: str) -> None:
        context.provenance["vision_stage"] = "skipped-no-model"
        context.provenance["vision_reason"] = reason

    def _review(self, context: contracts.RunContext, model_name: str, provider: str, review) -> None:
        shots = self._screenshots(context)
        seen_keys = {(f.kind, f.url, f.action) for f in context.findings}
        reviewed = 0
        for step, rel_path, png_bytes in shots:
            try:
                answer = review(png_bytes)
            except Exception as exc:
                context.provenance.setdefault("vision_errors", []).append(f"{rel_path}: {exc}")
                continue
            reviewed += 1
            if _looks_clean(answer):
                continue
            url = self._url_for_step(context, step)
            action = f"vision: review {os.path.basename(rel_path)}"
            key = ("visual", url, action)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            context.add_finding(
                stage=self.name, kind="visual", severity="P2", status=contracts.STATUS_CANDIDATE,
                title="vision model reports a visual defect", url=url, action=action,
                timestamp=_now_iso(), detail=answer.strip()[:500], confidence=0.5,
                evidence_refs=[rel_path],
            )
        context.provenance["vision_stage"] = "ran"
        context.provenance["vision_reviewed"] = reviewed
        context.provenance["vision_model"] = model_name
        context.provenance["vision_provider"] = provider

    def _screenshots(self, context: contracts.RunContext) -> list[tuple[int, str, bytes]]:
        evidence_dir = os.path.join(context.run_dir, contracts.ARTIFACT_EVIDENCE)
        if not os.path.isdir(evidence_dir):
            return []
        shots: list[tuple[int, str, bytes]] = []
        for basename in sorted(os.listdir(evidence_dir)):
            step = _screenshot_step(basename)
            if step is None:
                continue
            with open(os.path.join(evidence_dir, basename), "rb") as fh:
                data = fh.read()
            shots.append((step, f"{contracts.ARTIFACT_EVIDENCE}/{basename}", data))
        shots.sort(key=lambda item: item[0])
        return shots[:MAX_SCREENSHOTS]

    @staticmethod
    def _url_for_step(context: contracts.RunContext, step: int) -> str:
        for event in context.events:
            if event.step == step and event.url:
                return event.url
        return context.config.target_url
