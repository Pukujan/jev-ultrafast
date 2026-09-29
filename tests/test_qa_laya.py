"""Offline pins for the local Laya adapter. No test here may reach a real
service; the one live check is explicit-gated and skipped in CI. Tests inject
their own base URLs and fakes — the dev box may be running localdecide/ollama
and CI may not; absence must never be an implicit assumption."""

import os

import httpx
import pytest

from jev_ultrafast import model
from jev_ultrafast.qa import laya


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status
        self.is_error = status >= 400
        self.text = str(payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.is_error:
            raise httpx.HTTPStatusError("boom", request=None, response=None)


def test_flatten_golden_table():
    criteria = {
        "1": {"element": "[1] Sign in", "current_value": "", "role": "button"},
        "2": {"element": "[2] Where to?", "current_value": "", "role": "combobox"},
        "3": {"element": "[3] Cabin class", "current_value": "Economy", "role": "combobox"},
        "4": {"element": "[4] Remember me", "current_value": "", "role": "checkbox", "checked": True},
        "5": {"element": "[5] " + "x" * 80, "current_value": "y" * 50, "role": "textbox", "expanded": False},
    }
    body = {"model": "m", "state": {}, "questions": {
        "operation": {"type": "choice", "criteria": {"CLICK": "Click a thing.", "DONE": "Satisfied."}},
        "click_target": {"type": "choice", "criteria": dict(criteria)},
    }}
    flat = laya.flatten(body)
    got = flat["questions"]["click_target"]["criteria"]
    assert got["1"] == "[1] Sign in (button)"
    assert got["2"] == "[2] Where to? (combobox)"
    assert got["3"] == "[3] Cabin class (combobox) = 'Economy'"
    assert got["4"] == "[4] Remember me (checkbox) checked=true"
    assert got["5"] == f"[5] {'x' * 60} (textbox) = {'y' * 30!r} expanded=false"
    # operation strings pass through untouched; keys preserved
    assert flat["questions"]["operation"]["criteria"] == body["questions"]["operation"]["criteria"]
    assert set(got) == set(criteria)
    # the original body is untouched
    assert isinstance(body["questions"]["click_target"]["criteria"]["1"], dict)


def test_discover_ok_and_fields(monkeypatch):
    calls = []

    def fake_get(url, timeout=None):
        calls.append(url)
        if url.endswith("/healthz"):
            return FakeResponse({"ok": True, "backend": "laya-mlx", "max_options_per_question": 20})
        return FakeResponse({"models": [{"name": "laya-mlx"}]})

    monkeypatch.setattr(laya.httpx, "get", fake_get)
    info = laya.discover("http://127.0.0.1:59999")
    assert info["backend"] == "laya-mlx" and info["max_options_per_question"] == 20
    assert info["models"] == ["laya-mlx"]
    assert calls[0].endswith("/healthz")


def test_discover_fail_closed_paths(monkeypatch):
    def refuse(url, timeout=None):
        raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr(laya.httpx, "get", refuse)
    with pytest.raises(laya.LayaUnavailable) as error:
        laya.discover("http://127.0.0.1:59998")
    message = str(error.value)
    assert "git clone https://github.com/ChenneyZhuang/laya-browser-agent" in message
    assert "localdecide serve" in message


def test_discover_rejects_not_ok(monkeypatch):
    payload = FakeResponse({"ok": False, "error": "cold"})
    monkeypatch.setattr(laya.httpx, "get", lambda url, timeout=None: payload)
    with pytest.raises(laya.LayaUnavailable):
        laya.discover("http://127.0.0.1:59997")


def test_discover_refuses_non_loopback(monkeypatch):
    def never(*args, **kwargs):
        raise AssertionError("must not touch the network for remote hosts")

    monkeypatch.setattr(laya.httpx, "get", never)
    monkeypatch.setenv("LAYA_BASE_URL", "https://evil.example.com")
    with pytest.raises(laya.LayaUnavailable):
        laya.discover()
    with pytest.raises(laya.LayaUnavailable):
        laya.discover("http://10.0.0.1:8791")


def test_base_url_read_at_call_time(monkeypatch):
    def fake_get(url, timeout=None):
        if url.endswith("/healthz"):
            return FakeResponse({"ok": True, "backend": "b", "max_options_per_question": 3})
        return FakeResponse({"models": []})

    monkeypatch.setattr(laya.httpx, "get", fake_get)
    monkeypatch.setenv("LAYA_BASE_URL", "http://localhost:1234")
    assert laya.discover()["base_url"] == "http://localhost:1234"
    monkeypatch.setenv("LAYA_BASE_URL", "http://127.0.0.1:4321")
    assert laya.discover()["base_url"] == "http://127.0.0.1:4321"


def test_transport_sends_no_auth_and_uses_systemone(monkeypatch):
    posts = {}

    def fake_post(url, json=None, timeout=None, headers=None):
        posts["url"] = url
        posts["json"] = json
        posts["headers"] = headers
        return FakeResponse({"answers": {}, "model": "localdecide", "usage": {},
                             "latency_ms": 1, "backend": "laya-mlx"})

    monkeypatch.setattr(laya.httpx, "post", fake_post)
    transport = laya.LayaTransport("http://127.0.0.1:59990")
    body = {"model": "m", "state": {"page": {}}, "questions": {
        "operation": {"type": "choice", "criteria": {"CLICK": "c"}},
        "click_target": {"type": "choice", "criteria": {"1": {"element": "[1] Go", "role": "button"}}},
    }}
    result = transport.request(transport.prepare(body))
    assert posts["url"] == "http://127.0.0.1:59990/v1/systemone"
    assert posts["headers"] is None  # no Authorization anywhere
    assert "Authorization" not in str(posts)
    assert isinstance(posts["json"]["questions"]["click_target"]["criteria"]["1"], str)
    assert result["backend"] == "laya-mlx"


def test_transport_http_error_fails_closed(monkeypatch):
    payload = FakeResponse({"error": "bad"}, status=422)
    monkeypatch.setattr(laya.httpx, "post", lambda *args, **kwargs: payload)
    transport = laya.LayaTransport("http://127.0.0.1:59989")
    with pytest.raises(laya.LayaUnavailable):
        transport.request({"questions": {}})


def test_laya_decider_shape_without_any_decision_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("TEXT_MODEL_API_KEY", raising=False)

    def fake_post(url, json=None, timeout=None, headers=None):
        assert url.endswith("/v1/systemone")
        crit = json["questions"]["operation"]["criteria"]
        answers = {"operation": {
            "choice": "DONE",
            "probabilities": {k: (1.0 if k == "DONE" else 0.0) for k in crit},
            "confidence": 1.0,
        }}
        return FakeResponse({"answers": answers, "model": "localdecide", "usage": {},
                             "latency_ms": 2, "backend": "laya-mlx"})

    monkeypatch.setattr(laya.httpx, "post", fake_post)
    state = {
        "url": "https://x.test/", "title": "T", "text": "hi", "scroll": 0.0,
        "actions": [{"id": "a1", "kind": "click", "node": "n1", "label": "Go", "role": "button"}],
    }
    decision = laya.laya_decider("http://127.0.0.1:59988").decide(state, "goal", [])
    assert decision["operation"] == "DONE"
    assert decision["choice"] == "DONE"
    crit = decision["request"]["questions"]["click_target"]["criteria"]
    assert crit["1"].startswith("[1] Go")


def test_laya_live_only_with_explicit_gate():
    if os.environ.get("LAYA_LIVE_OK") != "1":
        pytest.skip("set LAYA_LIVE_OK=1 with a localdecide runtime running to exercise the real model")
    info = laya.discover()
    assert info["backend"]
    state = {
        "url": "https://x.test/", "title": "Login", "text": "Sign in", "scroll": 0.0,
        "actions": [
            {"id": "a1", "kind": "click", "node": "n1", "label": "Sign in", "role": "button"},
            {"id": "a2", "kind": "click", "node": "n2", "label": "Cancel", "role": "button"},
        ],
    }
    decision = laya.laya_decider().decide(state, "Open the sign-in control", [])
    operation_ids = {"CLICK": "", "DONE": "", "BLOCKED": ""}
    model.validate_choice(decision["raw_answers"]["operation"], operation_ids)
    assert decision["operation"] in {"CLICK", "DONE", "BLOCKED"}
