"""Decision-provider adapters. Laya uses its documented local Python API only."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any


class LayaAdapter:
    """Bridge to the optional ``laya`` package; no HTTP or Jev fallback exists."""

    def __init__(self, router: Any | None = None):
        if router is None:
            try:
                from laya import Router
            except ImportError as exc:
                raise RuntimeError("Laya mode requires the optional 'laya' Python package.") from exc
            router = Router()
        self.router = router

    def decide(self, state: dict, questions: dict) -> dict:
        result = self.router.predict(state, questions)
        if not isinstance(result, dict) or not isinstance(result.get("answers"), dict):
            raise ValueError("Laya returned no typed answers; no browser action executed.")
        return result


def select_runner(value: str | None = None) -> str:
    """Choose local Laya by default; Jev is an explicit alternate/comparison arm."""
    normalized = (value or "laya").strip().lower()
    normalized = {"l": "laya", "j": "jev"}.get(normalized, normalized)
    if normalized not in {"laya", "jev"}:
        raise ValueError(f"Unsupported exploration runner: {normalized}")
    return normalized


def configured_provider(name: str, router: Any | None = None):
    """Keep provider construction explicit; never infer a fallback provider."""
    if name == "laya":
        return LayaAdapter(router)
    if name in {"openrouter", "typesafe", "opencode"}:
        return name
    raise ValueError(f"Unsupported decision provider: {name}")


def touch_cli_key(key: str, record_path: Path | None = None) -> bool:
    """Refresh idle expiry only when the called model uses the exact CLI-owned key."""
    path = record_path or Path.home() / ".jev-ultrafast" / "key-cleanup.json"
    if not path.exists():
        return False
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        digest = hashlib.sha256(key.encode()).hexdigest()
        if digest != record.get("sha256"):
            return False
        record["last_used"] = time.time()
        path.write_text(json.dumps(record), encoding="utf-8")
        return True
    except (OSError, ValueError, TypeError):
        return False
