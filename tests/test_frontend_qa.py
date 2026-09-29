"""Deterministic contracts for the frontend QA bootstrap."""

from pathlib import Path
from random import Random

from jev_ultrafast.frontend_qa import (
    Page,
    cleanup_watch,
    discover_key_names,
    inspect_url,
    read_env_value,
    record_cli_key,
    remove_exact_env_key,
    write_artifacts,
)
from jev_ultrafast.providers import LayaAdapter, configured_provider, select_runner, touch_cli_key


def test_env_discovery_shows_only_name_and_prefix(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text("OPENROUTER_API_KEY=sk-secret-value\nUNRELATED=do-not-read\n", encoding="utf-8")
    assert discover_key_names(env, "openrouter") == [("OPENROUTER_API_KEY", "sk-s")]
    assert read_env_value(env, "OPENROUTER_API_KEY") == "sk-secret-value"


def test_provider_alias_match_is_stable_and_non_provider_is_ignored(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text("TYPE_SAFE_API_KEY=abcd1234\nOPEN_CODE_KEY=xyz\n", encoding="utf-8")
    assert discover_key_names(env, "typesafe") == [("TYPE_SAFE_API_KEY", "abcd")]
    assert discover_key_names(env, "typesafe") == discover_key_names(env, "typesafe")


def test_report_artifact_set_and_metamorphic_add_event(tmp_path: Path):
    events = [{"type": "navigate", "url": "https://example.test", "timestamp": "now"}]
    write_artifacts(tmp_path, "https://example.test", events, [], "openrouter", "jev")
    assert {p.name for p in tmp_path.iterdir()} == {"defects.csv", "workflow.mmd", "run.json", "report.html"}
    assert '"vision": "NOT RUN"' in (tmp_path / "run.json").read_text(encoding="utf-8")
    assert '"source_revision":' in (tmp_path / "run.json").read_text(encoding="utf-8")
    assert "Vision: NOT RUN" in (tmp_path / "report.html").read_text(encoding="utf-8")
    before = (tmp_path / "workflow.mmd").read_text(encoding="utf-8")
    events.append({"type": "response", "url": "https://example.test", "status": 200, "timestamp": "later"})
    write_artifacts(tmp_path, "https://example.test", events, [], "openrouter", "jev")
    after = (tmp_path / "workflow.mmd").read_text(encoding="utf-8")
    assert len(after.splitlines()) > len(before.splitlines())


def test_static_inspector_reports_unreachable_target(monkeypatch):
    def fail(_request, timeout):
        raise OSError("offline")

    monkeypatch.setattr("jev_ultrafast.frontend_qa.urlopen", fail)
    findings, events = inspect_url("http://127.0.0.1:1/")
    assert findings[0].kind == "navigation"
    assert events[0]["type"] == "navigate"


def test_cleanup_removes_only_exact_cli_inserted_value(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text("OPENROUTER_API_KEY=operator-key\nOPENROUTER_API_KEY=other-key\n", encoding="utf-8")
    import hashlib

    digest = hashlib.sha256(b"operator-key").hexdigest()
    assert remove_exact_env_key(env, "OPENROUTER_API_KEY", digest)
    assert env.read_text(encoding="utf-8") == "OPENROUTER_API_KEY=other-key\n"
    assert not remove_exact_env_key(env, "OPENROUTER_API_KEY", digest)


def test_key_use_refreshes_only_matching_cleanup_record(tmp_path: Path, monkeypatch):
    import hashlib
    import json

    record = tmp_path / "cleanup.json"
    record.write_text(
        json.dumps({"sha256": hashlib.sha256(b"owned-key").hexdigest(), "last_used": 1}),
        encoding="utf-8",
    )
    monkeypatch.setattr("jev_ultrafast.providers.time.time", lambda: 42)
    assert not touch_cli_key("other-key", record)
    assert touch_cli_key("owned-key", record)
    assert json.loads(record.read_text(encoding="utf-8"))["last_used"] == 42


def test_cleanup_opt_out_writes_no_watch_record(tmp_path: Path):
    record = tmp_path / "private" / "watch.json"
    env = tmp_path / ".env"
    assert not record_cli_key(record, env, "TYPESAFE_API_KEY", "keep-me", enabled=False, now=0)
    assert not record.exists()


def test_cleanup_record_can_resume_after_restart(tmp_path: Path):
    import hashlib
    import json

    env = tmp_path / ".env"
    env.write_text("OPENROUTER_API_KEY=resume-me\n", encoding="utf-8")
    record = tmp_path / "watch.json"
    record_cli_key(record, env, "OPENROUTER_API_KEY", "resume-me", enabled=True, now=20)
    payload = json.loads(record.read_text(encoding="utf-8"))
    assert payload["last_used"] == 20
    assert payload["sha256"] == hashlib.sha256(b"resume-me").hexdigest()


def test_watchdog_fake_clock_expires_and_recovers(tmp_path: Path):
    import hashlib
    import json

    env = tmp_path / ".env"
    env.write_text("OPENCODE_API_KEY=cli-key\n", encoding="utf-8")
    record = tmp_path / "watch.json"
    record.write_text(
        json.dumps(
            {
                "env_file": str(env),
                "name": "OPENCODE_API_KEY",
                "sha256": hashlib.sha256(b"cli-key").hexdigest(),
                "last_used": 10,
            }
        ),
        encoding="utf-8",
    )
    current_time = [10]
    sleeps = []

    def advance(seconds):
        sleeps.append(seconds)
        current_time[0] += seconds

    cleanup_watch(record, clock=lambda: current_time[0], sleep=advance)
    assert sum(sleeps) == 3 * 60 * 60
    assert env.read_text(encoding="utf-8") == ""
    assert not record.exists()


def test_laya_adapter_uses_only_documented_local_router_contract():
    class LocalRouter:
        def __init__(self):
            self.calls = []

        def predict(self, state, questions):
            self.calls.append((state, questions))
            return {"answers": {"operation": {"choice": "DONE"}}}

    router = LocalRouter()
    adapter = configured_provider("laya", router)
    result = adapter.decide({"text": "observed"}, {"operation": {"type": "choice"}})
    assert isinstance(adapter, LayaAdapter)
    assert result["answers"]["operation"]["choice"] == "DONE"
    assert router.calls == [({"text": "observed"}, {"operation": {"type": "choice"}})]


def test_default_exploration_runner_is_local_laya():
    assert select_runner() == "laya"
    assert select_runner("") == "laya"
    assert select_runner("j") == "jev"


def test_missing_laya_fails_without_jev_or_deterministic_fallback(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "laya", None)
    try:
        configured_provider(select_runner())
    except RuntimeError as exc:
        assert "requires the optional 'laya' Python package" in str(exc)
    else:
        raise AssertionError("missing Laya must fail closed")


def test_deterministic_dom_fuzz_keeps_link_and_control_counts():
    random = Random(9031)
    tags = ["button", "input", "select", "textarea"]
    for case in range(40):
        controls = [random.choice(tags) for _ in range(case % 9)]
        links = [f'<a href="/page-{case}-{i}">Link {i}</a>' for i in range(case % 7)]
        markup = "".join(f"<{tag} aria-label='control-{i}'></{tag}>" for i, tag in enumerate(controls))
        parser = Page()
        parser.feed("<html><body>" + markup + "".join(links) + "</body></html>")
        assert len(parser.controls) == len(controls)
        assert len(parser.links) == case % 7
