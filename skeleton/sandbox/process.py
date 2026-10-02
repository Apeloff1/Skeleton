"""Process isolation for untrusted commands (B082).

:func:`run_isolated` launches an argv (never a shell string) with:

* a scrubbed environment (allowlisted keys only; secrets never inherited);
* a private working directory inside an :class:`~.fs.FsJail`;
* POSIX resource limits applied in the child before ``exec`` — CPU seconds,
  address space, file size, open files, process count, core dumps off;
* its own session / process group, killed as a group on timeout;
* bounded stdout/stderr capture (excess is truncated, not buffered);
* optional network isolation via ``unshare --net`` when available
  (``network="deny"`` fails closed if it cannot be enforced).

Returns a :class:`ProcessResult`; never raises for a non-zero exit.
"""
from __future__ import annotations

import os
import selectors
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .errors import ProcessLimitError, ProcessPolicyError
from .fs import FsJail

SAFE_ENV_KEYS = frozenset({"LANG", "LC_ALL", "LC_CTYPE", "TZ", "TERM", "PYTHONHASHSEED", "PYTHONIOENCODING"})
_SECRET_HINTS = ("TOKEN", "SECRET", "PASSWORD", "PASSWD", "KEY", "CREDENTIAL", "AUTH", "COOKIE", "SESSION")
_DENIED_ENV_KEYS = frozenset({
    "PATH",
    "HOME",
    "TMPDIR",
    "PYTHONPATH",
    "PYTHONHOME",
    "VIRTUAL_ENV",
    "BASH_ENV",
    "ENV",
})
DEFAULT_PATH = "/usr/local/bin:/usr/bin:/bin"
MAX_ARGV = 256
MAX_ARG_CHARS = 32_768


@dataclass(frozen=True)
class ProcessLimits:
    wall_seconds: float = 10.0
    cpu_seconds: int = 5
    memory_bytes: int = 512 * 1024 * 1024
    file_bytes: int = 16 * 1024 * 1024
    open_files: int = 64
    processes: int | None = None  # RLIMIT_NPROC is per-user; opt-in only
    output_bytes: int = 1024 * 1024
    network: str = "inherit"  # "inherit" | "deny"

    def __post_init__(self) -> None:
        if self.wall_seconds <= 0 or self.cpu_seconds <= 0:
            raise ProcessPolicyError("time limits must be positive")
        if self.network not in {"inherit", "deny"}:
            raise ProcessPolicyError("network must be 'inherit' or 'deny'")


@dataclass
class ProcessResult:
    argv: tuple[str, ...]
    returncode: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool
    truncated: bool
    duration_s: float
    signal: int | None = None
    limits: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    def text(self) -> str:
        return self.stdout.decode("utf-8", errors="replace")

    def to_record(self) -> dict[str, Any]:
        return {
            "argv": list(self.argv), "returncode": self.returncode, "timed_out": self.timed_out,
            "truncated": self.truncated, "duration_s": round(self.duration_s, 4), "signal": self.signal,
            "stdout_bytes": len(self.stdout), "stderr_bytes": len(self.stderr), "limits": dict(self.limits),
        }


def scrub_env(extra: Mapping[str, str] | None = None, *, base: Mapping[str, str] | None = None) -> dict[str, str]:
    """Allowlisted environment; ``extra`` keys that look secret are refused."""
    src = os.environ if base is None else base
    env = {k: v for k, v in src.items() if k in SAFE_ENV_KEYS}
    env["PATH"] = DEFAULT_PATH
    env["PYTHONHASHSEED"] = env.get("PYTHONHASHSEED", "0")
    for key, value in (extra or {}).items():
        if not isinstance(key, str) or not key.replace("_", "").isalnum() or not isinstance(value, str):
            raise ProcessPolicyError("invalid environment entry", context={"key": repr(key)[:40]})
        upper = key.upper()
        if any(h in upper for h in _SECRET_HINTS):
            raise ProcessPolicyError("secret-looking environment keys cannot be passed into the sandbox", context={"key": key})
        if upper in _DENIED_ENV_KEYS or upper.startswith(("LD_", "DYLD_")):
            raise ProcessPolicyError("process-control environment key cannot be overridden", context={"key": key})
        if "\x00" in value:
            raise ProcessPolicyError("environment values may not contain NUL")
        env[key] = value
    return env


def check_argv(argv: Sequence[str]) -> tuple[str, ...]:
    if isinstance(argv, (str, bytes)) or not isinstance(argv, Sequence) or not argv:
        raise ProcessPolicyError("argv must be a non-empty list of strings (shell strings are refused)")
    if len(argv) > MAX_ARGV:
        raise ProcessPolicyError("too many arguments", context={"maximum": MAX_ARGV})
    out = []
    for a in argv:
        if not isinstance(a, str) or "\x00" in a or len(a) > MAX_ARG_CHARS:
            raise ProcessPolicyError("arguments must be NUL-free strings of bounded size")
        out.append(a)
    return tuple(out)


def _resolve_argv0(args: tuple[str, ...]) -> tuple[str, ...]:
    argv0 = args[0]
    if os.path.isabs(argv0):
        resolved = os.path.realpath(argv0)
        if not os.path.isfile(resolved) or not os.access(resolved, os.X_OK):
            raise ProcessPolicyError("executable is not a runnable regular file", context={"argv0": argv0})
    else:
        if "/" in argv0 or "\\" in argv0:
            raise ProcessPolicyError("relative executable paths are forbidden", context={"argv0": argv0})
        found = shutil.which(argv0, path=DEFAULT_PATH)
        if found is None:
            raise ProcessPolicyError("executable not found in trusted path", context={"argv0": argv0})
        resolved = os.path.realpath(found)
    return (resolved, *args[1:])


def _preexec(limits: ProcessLimits):
    def apply() -> None:  # runs in the child between fork and exec
        import resource

        os.setsid()
        pairs = [
            (resource.RLIMIT_CPU, limits.cpu_seconds),
            (resource.RLIMIT_FSIZE, limits.file_bytes),
            (resource.RLIMIT_NOFILE, limits.open_files),
            (resource.RLIMIT_CORE, 0),
        ]
        if hasattr(resource, "RLIMIT_AS"):
            pairs.append((resource.RLIMIT_AS, limits.memory_bytes))
        if limits.processes is not None and hasattr(resource, "RLIMIT_NPROC"):
            pairs.append((resource.RLIMIT_NPROC, limits.processes))
        for which, value in pairs:
            soft, hard = resource.getrlimit(which)
            cap = value if hard == resource.RLIM_INFINITY else min(value, hard)
            resource.setrlimit(which, (cap, cap))
        os.umask(0o077)

    return apply


def network_isolation_available() -> bool:
    exe = shutil.which("unshare", path=DEFAULT_PATH)
    if exe is None or not sys.platform.startswith("linux"):
        return False
    try:
        r = subprocess.run([exe, "--user", "--map-root-user", "--net", "true"], capture_output=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


def _kill_group(proc: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        try:
            proc.kill()
        except ProcessLookupError:
            pass


def run_isolated(
    argv: Sequence[str],
    *,
    jail: FsJail | None = None,
    cwd: str | None = None,
    stdin: bytes | None = None,
    env: Mapping[str, str] | None = None,
    limits: ProcessLimits | None = None,
) -> ProcessResult:
    """Run ``argv`` under the sandbox limits; see module docstring."""
    if os.name != "posix":
        raise ProcessPolicyError("process isolation requires POSIX")
    lim = limits or ProcessLimits()
    args = _resolve_argv0(check_argv(argv))
    owned = jail is None
    box = jail or FsJail.temporary(prefix="sbx-proc-")
    try:
        return _run(args, box, cwd, stdin, env, lim)
    finally:
        if owned:
            shutil.rmtree(box.root, ignore_errors=True)


def _run(args: tuple[str, ...], box: FsJail, cwd: str | None, stdin: bytes | None, env: Mapping[str, str] | None, lim: ProcessLimits) -> ProcessResult:
    workdir = box.root if not cwd else box.resolve(cwd, must_exist=True)
    if not workdir.is_dir():
        raise ProcessPolicyError("cwd must be a directory inside the jail")
    child_env = scrub_env(env)
    child_env["HOME"] = str(box.root)
    child_env["TMPDIR"] = str(box.root)
    launch = list(args)
    if lim.network == "deny":
        if not network_isolation_available():
            raise ProcessPolicyError("network isolation requested but unavailable (fail closed)")
        unshare = shutil.which("unshare", path=DEFAULT_PATH)
        if unshare is None:
            raise ProcessPolicyError("network isolation executable missing from trusted path")
        launch = [os.path.realpath(unshare), "--user", "--map-root-user", "--net", "--", *launch]

    started = time.monotonic()
    try:
        proc = subprocess.Popen(
            launch, cwd=workdir, env=child_env, stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, preexec_fn=_preexec(lim), close_fds=True,
        )
    except FileNotFoundError as exc:
        raise ProcessPolicyError("executable not found", context={"argv0": args[0]}) from exc
    if stdin is not None and proc.stdin is not None:
        try:
            proc.stdin.write(stdin[: lim.output_bytes])
        except BrokenPipeError:
            pass
        proc.stdin.close()

    out, err = bytearray(), bytearray()
    truncated = timed_out = False
    sel = selectors.DefaultSelector()
    assert proc.stdout is not None and proc.stderr is not None
    sel.register(proc.stdout, selectors.EVENT_READ, out)
    sel.register(proc.stderr, selectors.EVENT_READ, err)
    deadline = started + lim.wall_seconds
    while sel.get_map():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            timed_out = True
            _kill_group(proc)
            break
        for key, _ in sel.select(timeout=min(remaining, 0.1)):
            chunk = os.read(key.fd, 65536)
            if not chunk:
                sel.unregister(key.fileobj)
                continue
            buf: bytearray = key.data
            room = lim.output_bytes - len(buf)
            if room > 0:
                buf.extend(chunk[:room])
            if len(chunk) > room:
                truncated = True
    sel.close()
    try:
        rc = proc.wait(timeout=max(0.1, deadline - time.monotonic()))
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_group(proc)
        rc = proc.wait()
    _kill_group(proc)  # reap stragglers left in the group
    duration = time.monotonic() - started
    sig = -rc if rc is not None and rc < 0 else None
    return ProcessResult(args, rc, bytes(out), bytes(err), timed_out, truncated, duration, sig, {
        "wall_seconds": lim.wall_seconds, "cpu_seconds": lim.cpu_seconds, "memory_bytes": lim.memory_bytes,
        "file_bytes": lim.file_bytes, "open_files": lim.open_files, "network": lim.network,
    })


def require_ok(result: ProcessResult) -> ProcessResult:
    if result.timed_out:
        raise ProcessLimitError("sandboxed process timed out", context=result.to_record())
    return result


__all__ = [
    "SAFE_ENV_KEYS",
    "ProcessLimits",
    "ProcessResult",
    "check_argv",
    "network_isolation_available",
    "require_ok",
    "run_isolated",
    "scrub_env",
]
