"""Idle-key watchdog: a detached process that removes CLI-typed keys once
they sit idle past the TTL.

The CLI spawns it as `[sys.executable, "-m", "jev_ultrafast.qa.keywatch",
"--state", <abs state path>]` with stdio devnulled and a new session, so it
survives the CLI exiting. Removal is guarded: the recorded line comes out of
the env file only while its bytes still hash to the recorded value. A
retyped variable belongs to the operator; the watchdog marks the record
`skipped_changed` and leaves the file alone. Name alone is never grounds
for deletion.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

from jev_ultrafast.qa import contracts, providers

WATCH_POLL_SECONDS = 60.0


def pid_alive(pid) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        return _pid_alive_nt(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but belongs to someone else
    return True


def _pid_alive_nt(pid: int) -> bool:
    """Query liveness through kernel32; os.kill(pid, 0) raises WinError 87 on Windows.

    A pid that cannot be opened or queried counts as dead so the CLI respawns
    its watcher; the state-file lock keeps a duplicate from running twice.
    """
    import ctypes

    process_query_limited_information = 0x1000
    still_active = 259
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


def spawn_watcher(state_path):
    """Detach a watcher for the given state file and return the Popen handle.

    Always the current interpreter and an absolute state path: a bare
    `python` can resolve outside the venv, and a relative path breaks once
    the child's cwd differs.
    """
    abs_state = Path(state_path).resolve()
    return subprocess.Popen(
        [sys.executable, "-m", "jev_ultrafast.qa.keywatch", "--state", str(abs_state)],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _actionable(record: dict) -> bool:
    return not record.get("opted_out") and not record.get("skipped_changed")


def _process_due(state: dict, now: float) -> tuple[list[str], list[str]]:
    """Guarded delete for every due record. Returns (removed, skipped) names."""
    removed, skipped, remaining = [], [], []
    for record in state["records"]:
        if not _actionable(record):
            remaining.append(record)
            continue
        if now - record.get("last_used", now) < contracts.IDLE_KEY_TTL_SECONDS:
            remaining.append(record)
            continue
        if providers.guarded_remove(record) == "removed":
            removed.append(record["name"])
        else:
            record["skipped_changed"] = True
            skipped.append(record["name"])
            remaining.append(record)
    state["records"] = remaining
    return removed, skipped


def run_watcher(state_path, *, clock=time.time, sleep=time.sleep) -> dict:
    """Watch until no actionable record remains, then exit.

    Clock and sleep are injectable for tests. The watcher records its own
    pid on every pass and clears it on a clean exit.
    """
    state_path = Path(state_path)
    removed_total, skipped_total = [], []
    while True:
        try:
            with providers.locked(state_path, clock=clock, timeout=WATCH_POLL_SECONDS):
                state = providers.load_state(state_path)
                state["watcher_pid"] = os.getpid()
                removed, skipped = _process_due(state, clock())
                removed_total.extend(removed)
                skipped_total.extend(skipped)
                done = not any(_actionable(record) for record in state["records"])
                if done:
                    state["watcher_pid"] = None
                providers.save_state(state_path, state)
        except providers.LockBusy:
            sleep(WATCH_POLL_SECONDS)
            continue
        if done:
            return {"removed": removed_total, "skipped_changed": skipped_total}
        sleep(WATCH_POLL_SECONDS)


def reconcile(
    state_path, *, clock=time.time, spawn=spawn_watcher, lock_timeout: float = providers.LOCK_DEFAULT_TIMEOUT
) -> dict:
    """CLI-start reconciliation of the ledger.

    Expired inserts are removed with the same guard as the watcher. When
    actionable records remain, a missing or dead watcher is respawned and a
    live one is never duplicated. Returns a summary of what happened.
    """
    state_path = Path(state_path)
    with providers.locked(state_path, clock=clock, timeout=lock_timeout):
        state = providers.load_state(state_path)
        removed, skipped = _process_due(state, clock())
        respawned = False
        if any(_actionable(record) for record in state["records"]):
            if not pid_alive(state.get("watcher_pid")):
                process = spawn(state_path.resolve())
                state["watcher_pid"] = process.pid
                respawned = True
        else:
            state["watcher_pid"] = None
        providers.save_state(state_path, state)
        return {
            "removed": removed,
            "skipped_changed": skipped,
            "respawned": respawned,
            "watcher_pid": state.get("watcher_pid"),
        }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="jev_ultrafast.qa.keywatch", description="Idle-key watchdog.")
    parser.add_argument("--state", required=True, help="absolute path to keywatch.json")
    args = parser.parse_args(argv)
    run_watcher(Path(args.state).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
