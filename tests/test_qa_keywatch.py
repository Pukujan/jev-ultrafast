"""Offline tests for the idle-key watchdog.

Fake clock plus tmp files; no network, no browsers. Covers expiry of the
exact inserted line only, operator-retyped preservation, opt-out, use
refresh, restart recovery, reconcile, spawn dedupe, and spawn argv.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from jev_ultrafast.qa import contracts, keywatch, providers

TTL = contracts.IDLE_KEY_TTL_SECONDS
SECRET = "sk-or-v1-watch-secret"
REPO_ROOT = Path(__file__).resolve().parents[1]


class FakeClock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FakeProc:
    def __init__(self, pid=4242):
        self.pid = pid


def setup_key(tmp_path, clock, name="OPENROUTER_API_KEY", value=SECRET):
    env_file = tmp_path / ".env"
    env_file.write_text("PRE_EXISTING=keep\n", encoding="utf-8")
    state_path = tmp_path / "keywatch.json"
    record = providers.insert_key(env_file, name, value, state_path=state_path, clock=clock)
    return env_file, state_path, record


def dead_pid():
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


def test_expiry_removes_only_the_inserted_line(tmp_path):
    clock = FakeClock()
    env_file, state_path, record = setup_key(tmp_path, clock)
    clock.now += TTL + 1

    result = keywatch.run_watcher(state_path, clock=clock, sleep=clock.sleep)

    assert result["removed"] == [record["name"]]
    assert env_file.read_text() == "PRE_EXISTING=keep\n"
    state = providers.load_state(state_path)
    assert state["records"] == []
    assert state["watcher_pid"] is None


def test_expiry_waits_out_the_idle_window(tmp_path):
    clock = FakeClock()
    env_file, state_path, record = setup_key(tmp_path, clock)
    clock.now += TTL - 30  # not due on the first pass

    result = keywatch.run_watcher(state_path, clock=clock, sleep=clock.sleep)

    assert result["removed"] == [record["name"]]
    assert env_file.read_text() == "PRE_EXISTING=keep\n"
    # Nothing was removed early: exactly one poll elapsed before the delete.
    assert clock.now == 1000.0 + TTL - 30 + keywatch.WATCH_POLL_SECONDS


def test_retyped_key_is_preserved_and_marked_skipped(tmp_path):
    clock = FakeClock()
    env_file, state_path, record = setup_key(tmp_path, clock)
    env_file.write_text("PRE_EXISTING=keep\nOPENROUTER_API_KEY=operator-retyped\n", encoding="utf-8")
    clock.now += TTL + 1

    result = keywatch.run_watcher(state_path, clock=clock, sleep=clock.sleep)

    assert result["removed"] == []
    assert result["skipped_changed"] == [record["name"]]
    assert "OPENROUTER_API_KEY=operator-retyped" in env_file.read_text()
    state = providers.load_state(state_path)
    assert state["records"][0]["skipped_changed"] is True

    # A skipped record is terminal: later passes never retry the delete.
    clock.now += TTL * 3
    assert keywatch.run_watcher(state_path, clock=clock, sleep=clock.sleep) == {
        "removed": [],
        "skipped_changed": [],
    }


def test_opted_out_record_is_never_deleted(tmp_path):
    clock = FakeClock()
    env_file, state_path, record = setup_key(tmp_path, clock)
    state = providers.load_state(state_path)
    state["records"][0]["opted_out"] = True
    providers.save_state(state_path, state)
    clock.now += TTL * 10

    result = keywatch.run_watcher(state_path, clock=clock, sleep=clock.sleep)

    assert result == {"removed": [], "skipped_changed": []}
    assert f"OPENROUTER_API_KEY={SECRET}" in env_file.read_text()
    assert providers.load_state(state_path)["records"][0]["opted_out"] is True


def test_mark_used_refresh_defers_expiry(tmp_path):
    clock = FakeClock()
    env_file, state_path, record = setup_key(tmp_path, clock)

    clock.now += TTL - 60
    assert providers.mark_used(record["name"], SECRET, env_path=env_file, state_path=state_path, clock=clock)

    # Without the refresh this moment would already be past expiry.
    clock.now = 1000.0 + TTL + 1
    calls = []
    summary = keywatch.reconcile(state_path, clock=clock, spawn=lambda path: calls.append(path) or FakeProc())
    assert summary["removed"] == []
    assert f"OPENROUTER_API_KEY={SECRET}" in env_file.read_text()

    clock.now = 1000.0 + 2 * TTL
    summary = keywatch.reconcile(state_path, clock=clock, spawn=lambda path: calls.append(path) or FakeProc())
    assert summary["removed"] == [record["name"]]
    assert env_file.read_text() == "PRE_EXISTING=keep\n"


def test_restart_recovery_respawns_dead_watcher_from_state(tmp_path):
    clock = FakeClock()
    env_file, state_path, record = setup_key(tmp_path, clock)
    dead = dead_pid()
    assert not keywatch.pid_alive(dead)

    state = providers.load_state(state_path)
    state["watcher_pid"] = dead
    providers.save_state(state_path, state)

    spawned = []
    summary = keywatch.reconcile(state_path, clock=clock, spawn=lambda path: spawned.append(path) or FakeProc(777))

    assert summary["respawned"] is True
    assert summary["watcher_pid"] == 777
    assert spawned == [state_path.resolve()]
    assert summary["removed"] == []
    assert f"OPENROUTER_API_KEY={SECRET}" in env_file.read_text()


def test_reconcile_removes_expired_with_guard_and_no_respawn(tmp_path):
    clock = FakeClock()
    env_file, state_path, record = setup_key(tmp_path, clock)
    clock.now += TTL + 1

    calls = []
    summary = keywatch.reconcile(state_path, clock=clock, spawn=lambda path: calls.append(path) or FakeProc())

    assert summary["removed"] == [record["name"]]
    assert summary["skipped_changed"] == []
    assert summary["respawned"] is False
    assert summary["watcher_pid"] is None
    assert calls == []
    assert env_file.read_text() == "PRE_EXISTING=keep\n"


def test_lock_prevents_double_spawn(tmp_path):
    clock = FakeClock()
    env_file, state_path, record = setup_key(tmp_path, clock)

    # A live recorded watcher pid is never duplicated.
    state = providers.load_state(state_path)
    state["watcher_pid"] = os.getpid()
    providers.save_state(state_path, state)
    calls = []
    summary = keywatch.reconcile(state_path, clock=clock, spawn=lambda path: calls.append(path) or FakeProc())
    assert summary["respawned"] is False
    assert calls == []
    assert summary["watcher_pid"] == os.getpid()

    # While another live process holds the state lock, reconcile cannot run.
    lock = providers.lock_path_for(state_path)
    lock.write_text(str(os.getpid()), encoding="utf-8")
    os.utime(lock, (clock.now, clock.now))
    with pytest.raises(providers.LockBusy):
        keywatch.reconcile(state_path, clock=clock, spawn=lambda path: FakeProc(), lock_timeout=0.0)
    lock.unlink()


def test_pid_alive_distinguishes_live_dead_and_invalid():
    assert keywatch.pid_alive(os.getpid()) is True
    assert keywatch.pid_alive(dead_pid()) is False
    assert keywatch.pid_alive(None) is False
    assert keywatch.pid_alive(0) is False
    assert keywatch.pid_alive("123") is False


def test_spawn_argv_uses_current_interpreter_and_absolute_state(tmp_path, monkeypatch):
    captured = {}

    class FakePopen:
        def __init__(self, argv, **kwargs):
            captured["argv"] = argv
            captured["kwargs"] = kwargs
            self.pid = 31337

    monkeypatch.setattr(subprocess, "Popen", FakePopen)
    monkeypatch.chdir(tmp_path)
    proc = keywatch.spawn_watcher(Path("keywatch.json"))

    assert proc.pid == 31337
    argv = captured["argv"]
    assert argv[0] == sys.executable
    assert argv[1:3] == ["-m", "jev_ultrafast.qa.keywatch"]
    assert argv[3] == "--state"
    assert argv[4] == str(tmp_path / "keywatch.json")
    assert os.path.isabs(argv[4])
    kwargs = captured["kwargs"]
    assert kwargs["start_new_session"] is True
    assert kwargs["stdin"] == subprocess.DEVNULL
    assert kwargs["stdout"] == subprocess.DEVNULL
    assert kwargs["stderr"] == subprocess.DEVNULL


def test_module_run_removes_expired_key_end_to_end(tmp_path):
    clock = FakeClock()
    env_file, state_path, record = setup_key(tmp_path, clock)
    state = providers.load_state(state_path)
    state["records"][0]["last_used"] = time.time() - TTL - 5  # already idle
    providers.save_state(state_path, state)

    proc = subprocess.run(
        [sys.executable, "-m", "jev_ultrafast.qa.keywatch", "--state", str(state_path)],
        capture_output=True,
        timeout=60,
        cwd=str(REPO_ROOT),
    )

    assert proc.returncode == 0, proc.stderr.decode()
    assert env_file.read_text() == "PRE_EXISTING=keep\n"
    assert providers.load_state(state_path)["records"] == []
