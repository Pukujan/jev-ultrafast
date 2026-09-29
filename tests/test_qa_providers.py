"""Offline tests for provider discovery and the keywatch ledger.

No network, no browsers, no paid APIs. Every test is self-contained with
tmp paths and an injected clock.
"""

import hashlib
import json
import os

import pytest

from jev_ultrafast.qa import providers

SECRET = "sk-or-v1-super-secret-value"


def write_env(path, text):
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def env_file(tmp_path):
    return tmp_path / ".env"


@pytest.fixture
def state_file(tmp_path):
    return tmp_path / "qa-runs" / "keywatch.json"


@pytest.fixture
def clean_env(monkeypatch):
    for name in providers.known_names():
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("QA_ENV_FILE", raising=False)
    return monkeypatch


def test_env_file_path_honors_override_and_default(clean_env, env_file):
    clean_env.setenv("QA_ENV_FILE", str(env_file))
    assert providers.env_file_path() == env_file.resolve()
    clean_env.delenv("QA_ENV_FILE")
    assert providers.env_file_path() == providers.repo_root() / ".env"


def test_discovery_reports_names_only_from_file_and_process(clean_env, env_file):
    write_env(env_file, f"OPENROUTER_API_KEY={SECRET}\nVISION_MODEL=qwen2.5-vl\nUNRELATED=1\n")
    clean_env.setenv("QA_ENV_FILE", str(env_file))
    clean_env.setenv("TEXT_MODEL_API_KEY", "another-secret")
    clean_env.setenv("VISION_MODEL", "qwen2.5-vl")

    found = providers.discover()
    by_name = {entry["name"]: entry for entry in found}

    assert by_name["OPENROUTER_API_KEY"] == {
        "name": "OPENROUTER_API_KEY",
        "provider": "openrouter",
        "sources": ("env-file",),
    }
    assert by_name["TEXT_MODEL_API_KEY"]["sources"] == ("process",)
    assert by_name["VISION_MODEL"]["sources"] == ("env-file", "process")
    assert by_name["VISION_MODEL"]["provider"] == "vision"
    assert "UNRELATED" not in by_name

    dumped = json.dumps(found)
    assert SECRET not in dumped
    assert "another-secret" not in dumped


def test_discovery_scoped_to_one_provider(clean_env, env_file):
    write_env(env_file, "TYPESAFE_API_KEY=ts\nOPENROUTER_API_KEY=or\n")
    found = providers.discover("typesafe", env_path=env_file)
    assert [entry["name"] for entry in found] == ["TYPESAFE_API_KEY"]


def test_match_name_exact_then_fuzzy_then_none():
    assert providers.match_name("OPENROUTER_API_KEY") == "OPENROUTER_API_KEY"
    assert providers.match_name("TEXT_MODEL_BASEURL") == "TEXT_MODEL_BASE_URL"
    assert providers.match_name("TOTALLY_UNKNOWN_NAME_XYZ") is None


def test_prefix_hint_labels_family_without_echoing_value():
    value = "sk-or-v1-abcdef"
    hint = providers.prefix_hint(value)
    assert "openrouter" in hint
    assert value not in hint and "abcdef" not in hint
    groq = providers.prefix_hint("gsk_123")
    assert "groq" in groq and "no supported arm" in groq
    assert providers.prefix_hint("xyz-123") is None


def test_confirm_candidate_names_variable_not_value():
    prompts = []
    assert providers.confirm_candidate("OPENROUTER_API_KEY", ask=lambda p: prompts.append(p) or "y") is True
    assert "OPENROUTER_API_KEY" in prompts[0]
    assert SECRET not in prompts[0]
    assert providers.confirm_candidate("OPENROUTER_API_KEY", ask=lambda p: "") is False
    assert providers.confirm_candidate("OPENROUTER_API_KEY", ask=lambda p: "n") is False


def test_secure_entry_uses_getpass_without_echo():
    seen = []
    value = providers.secure_entry("TYPESAFE_API_KEY", getpass_fn=lambda p: seen.append(p) or SECRET)
    assert value == SECRET
    assert "TYPESAFE_API_KEY" in seen[0]


def test_insert_appends_one_exact_line_and_records_state(env_file, state_file):
    write_env(env_file, "PRE_EXISTING=keep\n")
    record = providers.insert_key(env_file, "OPENROUTER_API_KEY", SECRET, state_path=state_file, clock=lambda: 100.0)

    assert env_file.read_text() == f"PRE_EXISTING=keep\nOPENROUTER_API_KEY={SECRET}\n"
    assert record["name"] == "OPENROUTER_API_KEY"
    assert record["env_path"] == str(env_file.resolve())
    # Identity covers the NAME=value content, not the newline style.
    assert record["line_sha256"] == hashlib.sha256(f"OPENROUTER_API_KEY={SECRET}".encode()).hexdigest()
    assert record["inserted_at"] == 100.0
    assert record["last_used"] == 100.0
    assert record["opted_out"] is False

    state = json.loads(state_file.read_text())
    assert state["records"] == [record]
    assert not providers.lock_path_for(state_file).exists()


def test_insert_creates_missing_env_file(tmp_path, state_file):
    env_file = tmp_path / "new.env"
    record = providers.insert_key(env_file, "VISION_API_KEY", "v", state_path=state_file)
    assert env_file.read_text() == "VISION_API_KEY=v\n"
    assert record["line_sha256"] == hashlib.sha256(b"VISION_API_KEY=v").hexdigest()


def test_insert_separates_file_without_trailing_newline(env_file, state_file):
    write_env(env_file, "A=1")
    providers.insert_key(env_file, "VISION_API_KEY", "v", state_path=state_file)
    assert env_file.read_text() == "A=1\nVISION_API_KEY=v\n"


def test_insert_refuses_to_touch_existing_variable(env_file, state_file):
    write_env(env_file, f"OPENROUTER_API_KEY={SECRET}\n")
    before = env_file.read_bytes()
    with pytest.raises(ValueError, match="stays untouched"):
        providers.insert_key(env_file, "OPENROUTER_API_KEY", "other-value", state_path=state_file)
    assert env_file.read_bytes() == before
    assert not state_file.exists()


def test_insert_rejects_invalid_variable_name(env_file, state_file):
    with pytest.raises(ValueError):
        providers.insert_key(env_file, "NOT A NAME", "v", state_path=state_file)


def test_mark_used_refreshes_only_for_recorded_line(env_file, state_file):
    now = [100.0]
    clock = lambda: now[0]  # noqa: E731
    providers.insert_key(env_file, "OPENROUTER_API_KEY", SECRET, state_path=state_file, clock=clock)

    now[0] = 250.0
    assert providers.mark_used("OPENROUTER_API_KEY", SECRET, env_path=env_file, state_path=state_file, clock=clock)
    assert providers.load_state(state_file)["records"][0]["last_used"] == 250.0

    # Operator retypes the variable: no refresh, even with the new value.
    write_env(env_file, "OPENROUTER_API_KEY=retyped-by-operator\n")
    now[0] = 300.0
    assert not providers.mark_used(
        "OPENROUTER_API_KEY", "retyped-by-operator", env_path=env_file, state_path=state_file, clock=clock
    )
    assert providers.load_state(state_file)["records"][0]["last_used"] == 250.0

    # Restored inserted bytes: a wrong value still does not refresh.
    write_env(env_file, f"OPENROUTER_API_KEY={SECRET}\n")
    assert not providers.mark_used(
        "OPENROUTER_API_KEY", "wrong-value", env_path=env_file, state_path=state_file, clock=clock
    )
    assert providers.mark_used("OPENROUTER_API_KEY", SECRET, env_path=env_file, state_path=state_file, clock=clock)
    assert not providers.mark_used("UNKNOWN_NAME", "x", env_path=env_file, state_path=state_file, clock=clock)


def test_fresh_lock_blocks_and_stale_lock_is_taken_over(state_file):
    lock = providers.lock_path_for(state_file)
    lock.parent.mkdir(parents=True)
    lock.write_text(str(os.getpid()), encoding="utf-8")

    os.utime(lock, (999.0, 999.0))
    with pytest.raises(providers.LockBusy):
        with providers.locked(state_file, clock=lambda: 1000.0, timeout=0.0):
            pass

    os.utime(lock, (900.0, 900.0))  # 100s old: past the 60s staleness window
    with providers.locked(state_file, clock=lambda: 1000.0, timeout=0.0):
        assert lock.read_text() == str(os.getpid())
    assert not lock.exists()


def test_state_survives_reload_for_restart_recovery(env_file, state_file):
    providers.insert_key(env_file, "OPENROUTER_API_KEY", SECRET, state_path=state_file, clock=lambda: 42.0)
    state = providers.load_state(state_file)
    assert state["watcher_pid"] is None
    assert state["records"][0]["inserted_at"] == 42.0
    # Corrupt state falls back to an empty ledger instead of crashing.
    state_file.write_text("{not json", encoding="utf-8")
    assert providers.load_state(state_file) == {"watcher_pid": None, "records": []}


def test_crlf_editor_save_keeps_the_inserted_line_identifiable(env_file, state_file):
    now = [100.0]
    clock = lambda: now[0]  # noqa: E731
    providers.insert_key(env_file, "OPENROUTER_API_KEY", SECRET, state_path=state_file, clock=clock)
    # A Windows editor re-saves the file with CRLF endings; that is not an operator retyping.
    env_file.write_bytes(env_file.read_bytes().replace(b"\n", b"\r\n"))

    now[0] = 250.0
    assert providers.mark_used("OPENROUTER_API_KEY", SECRET, env_path=env_file, state_path=state_file, clock=clock)
    assert providers.load_state(state_file)["records"][0]["last_used"] == 250.0
    record = providers.load_state(state_file)["records"][0]
    assert providers.guarded_remove(record) == "removed"
    assert "OPENROUTER_API_KEY" not in providers.read_env_names(env_file)

    # A retyped value under CRLF endings is still the operator's own credential.
    providers.insert_key(env_file, "VISION_API_KEY", "vv", state_path=state_file, clock=clock)
    record = providers.load_state(state_file)["records"][-1]
    env_file.write_bytes(b"VISION_API_KEY=operator-value\r\n")
    assert providers.guarded_remove(record) == "skipped_changed"
    assert providers.read_env_value("VISION_API_KEY", env_path=env_file) == "operator-value"
