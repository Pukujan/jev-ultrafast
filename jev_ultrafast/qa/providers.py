"""Provider credential discovery and the keywatch ledger.

Discovery scans variable names only: the jev package's own ignored `.env`
file (override its location with `QA_ENV_FILE`) plus the process
environment. Values never appear in a return value, prompt, or log line
from this module. A CLI-typed key may be inserted into the `.env` file as
one exact line, and that exact line is the only thing the idle-key
watchdog (`keywatch.py`) may later remove. Pre-existing variables are
never touched.
"""

from __future__ import annotations

import difflib
import getpass
import hashlib
import json
import os
import re
import time
from contextlib import contextmanager
from pathlib import Path

from jev_ultrafast.qa import contracts

LOCK_STALE_SECONDS = 60.0  # a lockfile older than this is taken over
LOCK_DEFAULT_TIMEOUT = 10.0

_ENV_NAME_RE = re.compile(rb"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")
_VALID_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# Value-prefix heuristics only. They label a typed value by family so the
# operator can confirm the right arm was chosen; the value itself is never
# echoed back.
KEY_PREFIX_HINTS: tuple[tuple[str, str], ...] = (
    ("sk-or-", "openrouter"),
    ("sk-airo-", "openrouter"),
    ("gsk_", "groq"),
)

_NAME_TO_PROVIDER = {
    name: provider for provider, names in contracts.PROVIDER_ENV_ALIASES.items() for name in names
}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def env_file_path() -> Path:
    """The package `.env` the Jev arm reads: `QA_ENV_FILE` override, else the repo-root `.env`."""
    override = os.environ.get("QA_ENV_FILE")
    if override:
        return Path(override).expanduser().resolve()
    return repo_root() / ".env"


def state_file_path() -> Path:
    """The watchdog ledger lives under the ignored qa-runs root."""
    return repo_root() / "qa-runs" / contracts.KEYWATCH_STATE


def known_names(provider: str | None = None) -> set[str]:
    if provider is None:
        return set(_NAME_TO_PROVIDER)
    return set(contracts.PROVIDER_ENV_ALIASES.get(provider, ()))


def match_name(candidate: str, *, provider: str | None = None) -> str | None:
    """Resolve a variable name: exact match first, then difflib similarity."""
    pool = sorted(known_names(provider))
    if candidate in pool:
        return candidate
    close = difflib.get_close_matches(candidate, pool, n=1, cutoff=0.6)
    return close[0] if close else None


def read_env_names(env_path) -> list[str]:
    """Variable names present in the file, in order. Values are never read."""
    try:
        raw = Path(env_path).read_bytes()
    except OSError:
        return []
    return [m.group(1).decode() for line in raw.splitlines() if (m := _ENV_NAME_RE.match(line))]


def _find_line(env_path, name: str) -> bytes | None:
    """Raw bytes of the first line assigning `name`, newline included."""
    try:
        raw = Path(env_path).read_bytes()
    except OSError:
        return None
    pattern = re.compile(rb"^\s*" + re.escape(name.encode()) + rb"\s*=")
    for line in raw.splitlines(keepends=True):
        if pattern.match(line):
            return line
    return None


def read_env_value(name: str, *, env_path=None) -> str | None:
    """Value stored for `name` in the env file, or None. Callers never log this return."""
    line = _find_line(env_path if env_path is not None else env_file_path(), name)
    if line is None:
        return None
    return line.decode(errors="replace").split("=", 1)[1].rstrip("\r\n")


def discover(provider: str | None = None, *, env_path=None) -> list[dict]:
    """Known variable names found in the env file or process environment.

    Names and locations only; this function never reads a value.
    """
    path = Path(env_path) if env_path is not None else env_file_path()
    file_names = set(read_env_names(path))
    found = []
    for name in sorted(known_names(provider)):
        sources = []
        if name in file_names:
            sources.append("env-file")
        if name in os.environ:
            sources.append("process")
        if sources:
            found.append({"name": name, "provider": _NAME_TO_PROVIDER[name], "sources": tuple(sources)})
    return found


def prefix_hint(value: str) -> str | None:
    """Label a typed value's key family without echoing the value itself."""
    for prefix, provider in KEY_PREFIX_HINTS:
        if value.startswith(prefix):
            if provider in contracts.PROVIDER_ENV_ALIASES:
                return f"looks like a key for {provider}"
            return f"looks like a key for {provider}, which no supported arm uses"
    return None


def confirm_candidate(name: str, *, ask=input) -> bool:
    """Ask the operator about a candidate variable by name; the value stays hidden."""
    reply = ask(f"Use {name} for this run? [y/N] ").strip().lower()
    return reply in ("y", "yes")


def secure_entry(name: str, *, getpass_fn=getpass.getpass) -> str:
    """Type a key without echoing it."""
    return getpass_fn(f"Type {name} (input hidden): ")


# --- keywatch ledger: state file plus lock ---------------------------------


def lock_path_for(state_path) -> Path:
    return Path(f"{state_path}.lock")


def acquire_lock(lock_path, *, now: float | None = None) -> int | None:
    """Create the lockfile with O_CREAT|O_EXCL and record our pid.

    Returns the pid on success, or None while a fresh lock is held. A lock
    older than LOCK_STALE_SECONDS is taken over so a crashed holder cannot
    wedge the ledger.
    """
    lock_path = Path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    now = time.time() if now is None else now
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        try:
            age = now - lock_path.stat().st_mtime
        except OSError:
            return None
        if age < LOCK_STALE_SECONDS:
            return None
        try:
            lock_path.unlink()
        except OSError:
            return None
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            return None
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    return os.getpid()


def release_lock(lock_path, *, pid: int | None = None) -> None:
    pid = os.getpid() if pid is None else pid
    lock_path = Path(lock_path)
    try:
        if lock_path.read_text(encoding="utf-8").strip() == str(pid):
            lock_path.unlink()
    except OSError:
        pass


class LockBusy(RuntimeError):
    """The keywatch state lock is held by another live process."""


@contextmanager
def locked(state_path, *, clock=time.time, timeout: float = LOCK_DEFAULT_TIMEOUT, poll: float = 0.02):
    """Hold the exclusive state lock around a ledger read-modify-write."""
    lock_path = lock_path_for(state_path)
    deadline = clock() + timeout
    while acquire_lock(lock_path, now=clock()) is None:
        if clock() >= deadline:
            raise LockBusy(f"keywatch state lock is held: {lock_path.name}")
        time.sleep(poll)
    try:
        yield
    finally:
        release_lock(lock_path)


def load_state(state_path) -> dict:
    state = {"watcher_pid": None, "records": []}
    try:
        raw = Path(state_path).read_text(encoding="utf-8")
    except OSError:
        return state
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return state
    if isinstance(data, dict):
        if isinstance(data.get("watcher_pid"), int):
            state["watcher_pid"] = data["watcher_pid"]
        records = data.get("records")
        if isinstance(records, list):
            state["records"] = [record for record in records if isinstance(record, dict)]
    return state


def save_state(state_path, state: dict) -> None:
    state_path = Path(state_path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_path.with_name(state_path.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, state_path)


# --- insertion and use tracking --------------------------------------------


def insert_key(env_path, name: str, value: str, *, state_path=None, clock=time.time) -> dict:
    """Append one exact `NAME=value` line to the env file and record it in the ledger.

    Refuses to touch an existing variable of the same name. Returns the
    appended record: name, env_path, line_sha256 (hash of the exact inserted
    line bytes), inserted_at, last_used, opted_out.
    """
    env_path = Path(env_path)
    state_path = Path(state_path) if state_path is not None else state_file_path()
    if not _VALID_NAME_RE.fullmatch(name):
        raise ValueError(f"{name} is not a valid variable name.")
    if name in read_env_names(env_path):
        raise ValueError(f"{name} is already set in {env_path.name}; the existing value stays untouched.")
    now = clock()
    line = f"{name}={value}\n".encode()
    env_path.parent.mkdir(parents=True, exist_ok=True)
    separator = b""
    if env_path.exists():
        existing = env_path.read_bytes()
        if existing and not existing.endswith(b"\n"):
            separator = b"\n"
    with open(env_path, "ab") as handle:
        handle.write(separator + line)
    record = {
        "name": name,
        "env_path": str(env_path.resolve()),
        "line_sha256": hashlib.sha256(line).hexdigest(),
        "inserted_at": now,
        "last_used": now,
        "opted_out": False,
    }
    with locked(state_path, clock=clock):
        state = load_state(state_path)
        state["records"].append(record)
        save_state(state_path, state)
    return record


def mark_used(name: str, value: str, *, env_path=None, state_path=None, clock=time.time) -> bool:
    """Refresh last_used for a ledger record.

    Refreshes only when the env file's current line for `name` still hashes
    to the recorded inserted line and still carries `value`; a retyped
    variable belongs to the operator and is left alone.
    """
    env_path = Path(env_path) if env_path is not None else env_file_path()
    state_path = Path(state_path) if state_path is not None else state_file_path()
    with locked(state_path, clock=clock):
        state = load_state(state_path)
        line = _find_line(env_path, name)
        if line is None:
            return False
        digest = hashlib.sha256(line).hexdigest()
        for record in state["records"]:
            if record.get("name") != name or record.get("skipped_changed"):
                continue
            if record.get("line_sha256") != digest:
                continue
            if read_env_value(name, env_path=env_path) != value:
                return False
            record["last_used"] = clock()
            save_state(state_path, state)
            return True
        return False


def guarded_remove(record: dict) -> str:
    """Remove the recorded line from its env file only while the bytes still
    hash to the recorded value. Other lines are never touched.

    Returns "removed", or "skipped_changed" when the line is missing or no
    longer matches (the operator retyped it with their own credential).
    """
    try:
        env_path = Path(record["env_path"])
        raw = env_path.read_bytes()
    except (KeyError, OSError):
        return "skipped_changed"
    lines = raw.splitlines(keepends=True)
    pattern = re.compile(rb"^\s*" + re.escape(str(record.get("name", "")).encode()) + rb"\s*=")
    for index, line in enumerate(lines):
        if pattern.match(line) and hashlib.sha256(line).hexdigest() == record.get("line_sha256"):
            env_path.write_bytes(b"".join(lines[:index] + lines[index + 1 :]))
            return "removed"
    return "skipped_changed"
