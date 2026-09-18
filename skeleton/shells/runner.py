"""Bounded, argv-only host process execution.

The runner is deliberately small and policy-first. It never invokes a command
through a shell, never performs ambient PATH lookup, and never inherits the
entire parent environment. Callers must register absolute executable paths and
explicitly choose which environment keys and working-directory roots are safe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import signal
import subprocess
import threading
import time
from types import MappingProxyType
from typing import Mapping

_ENV_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_COMMAND_KEY = re.compile(r"^[A-Za-z0-9_.+-]+$")
_READ_CHUNK = 16 * 1024


class ShellPolicyError(ValueError):
    """Raised when a command violates the local shell policy."""


class ShellExecutionError(RuntimeError):
    """Raised by :meth:`ShellRunner.run_checked` for an unsuccessful command."""

    def __init__(self, result: "ShellResult") -> None:
        self.result = result
        reason = "timed out" if result.timed_out else "exceeded output limit" if result.output_limited else "failed"
        super().__init__(f"shell command {result.command!r} {reason} (returncode={result.returncode})")


def _resolved_directory(path: Path) -> Path:
    try:
        resolved = path.expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ShellPolicyError("working-directory root does not exist") from exc
    if not resolved.is_dir():
        raise ShellPolicyError("working-directory root must be a directory")
    return resolved


def _executable_identity(path: str) -> tuple[int, int, int, int, int]:
    try:
        stat = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise ShellPolicyError("registered executable is unavailable") from exc
    if not Path(path).is_file():
        raise ShellPolicyError("registered executable must remain a file")
    return (
        int(stat.st_dev),
        int(stat.st_ino),
        int(stat.st_mode),
        int(stat.st_size),
        int(stat.st_mtime_ns),
    )


def _resolved_executable(path: str) -> str:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        raise ShellPolicyError("executables must be registered with absolute paths")
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ShellPolicyError("registered executable does not exist") from exc
    if not resolved.is_file():
        raise ShellPolicyError("registered executable must be a file")
    return str(resolved)


@dataclass(frozen=True)
class ShellPolicy:
    """Immutable execution policy for :class:`ShellRunner`.

    ``executables`` maps a short logical command name to an absolute executable
    path. The logical name is what callers use, avoiding ambient ``PATH`` lookup.
    ``allowed_env`` is the complete set of environment keys that may reach a
    child. ``inherited_env`` is the subset copied from the parent process.
    """

    executables: Mapping[str, str]
    cwd_roots: tuple[Path, ...]
    allowed_env: frozenset[str] = frozenset()
    inherited_env: frozenset[str] = frozenset()
    default_timeout: float = 10.0
    max_timeout: float = 60.0
    max_output_bytes: int = 1_048_576
    max_input_bytes: int = 1_048_576
    max_env_bytes: int = 32_768
    max_args: int = 128
    max_arg_bytes: int = 65_536

    def __post_init__(self) -> None:
        if not self.executables:
            raise ShellPolicyError("at least one executable must be registered")
        normalized: dict[str, str] = {}
        identities: dict[str, tuple[int, int, int, int, int]] = {}
        for name, path in self.executables.items():
            if not isinstance(name, str) or not _COMMAND_KEY.fullmatch(name):
                raise ShellPolicyError("invalid executable policy key")
            if not isinstance(path, str):
                raise ShellPolicyError("executable paths must be strings")
            resolved = _resolved_executable(path)
            normalized[name] = resolved
            identities[name] = _executable_identity(resolved)
        roots = tuple(_resolved_directory(Path(root)) for root in self.cwd_roots)
        if not roots:
            raise ShellPolicyError("at least one working-directory root is required")
        if self.default_timeout <= 0 or self.max_timeout <= 0 or self.default_timeout > self.max_timeout:
            raise ShellPolicyError("timeout bounds are invalid")
        if self.max_output_bytes <= 0 or self.max_input_bytes < 0 or self.max_env_bytes <= 0:
            raise ShellPolicyError("I/O bounds are invalid")
        if self.max_args <= 0 or self.max_arg_bytes <= 0:
            raise ShellPolicyError("argument bounds are invalid")
        allowed_env = frozenset(self.allowed_env)
        inherited_env = frozenset(self.inherited_env)
        for key in allowed_env | inherited_env:
            if not isinstance(key, str) or not _ENV_KEY.fullmatch(key):
                raise ShellPolicyError("invalid environment variable name in policy")
        if not inherited_env <= allowed_env:
            raise ShellPolicyError("inherited_env must be a subset of allowed_env")
        object.__setattr__(self, "executables", MappingProxyType(normalized))
        object.__setattr__(
            self,
            "_executable_identities",
            MappingProxyType(identities),
        )
        object.__setattr__(self, "cwd_roots", roots)
        object.__setattr__(self, "allowed_env", allowed_env)
        object.__setattr__(self, "inherited_env", inherited_env)


@dataclass(frozen=True)
class ShellCommand:
    command: str
    args: tuple[str, ...] = ()
    cwd: Path | None = None
    env: Mapping[str, str] = field(default_factory=dict)
    stdin: bytes | None = None
    timeout: float | None = None
    allowed_returncodes: frozenset[int] = frozenset({0})

    def __post_init__(self) -> None:
        object.__setattr__(self, "args", tuple(self.args))
        object.__setattr__(self, "env", MappingProxyType(dict(self.env)))
        object.__setattr__(self, "allowed_returncodes", frozenset(self.allowed_returncodes))


@dataclass(frozen=True)
class ShellResult:
    command: str
    returncode: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool = False
    output_limited: bool = False
    accepted: bool = False

    @property
    def ok(self) -> bool:
        return self.accepted and not self.timed_out and not self.output_limited

    def stdout_text(self, encoding: str = "utf-8") -> str:
        return self.stdout.decode(encoding, errors="replace")

    def stderr_text(self, encoding: str = "utf-8") -> str:
        return self.stderr.decode(encoding, errors="replace")


class ShellRunner:
    """Execute commands under a fixed :class:`ShellPolicy`."""

    def __init__(self, policy: ShellPolicy) -> None:
        self.policy = policy

    @staticmethod
    def _within(path: Path, roots: tuple[Path, ...]) -> bool:
        return any(path == root or root in path.parents for root in roots)

    def _cwd(self, cwd: Path | None) -> Path:
        selected = self.policy.cwd_roots[0] if cwd is None else Path(cwd)
        try:
            resolved = selected.expanduser().resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise ShellPolicyError("working directory does not exist") from exc
        if not resolved.is_dir() or not self._within(resolved, self.policy.cwd_roots):
            raise ShellPolicyError("working directory is outside allowed roots")
        return resolved

    def _argv(self, command: ShellCommand) -> list[str]:
        executable = self.policy.executables.get(command.command)
        if executable is None:
            raise ShellPolicyError("command is not registered")
        expected_identity = self.policy._executable_identities.get(command.command)
        if expected_identity is None or _executable_identity(executable) != expected_identity:
            raise ShellPolicyError(
                "registered executable changed after policy construction"
            )
        if len(command.args) > self.policy.max_args:
            raise ShellPolicyError("too many command arguments")
        argv = [executable]
        total = 0
        for arg in command.args:
            if not isinstance(arg, str):
                raise ShellPolicyError("all command arguments must be strings")
            if "\x00" in arg:
                raise ShellPolicyError("command arguments may not contain NUL")
            total += len(arg.encode("utf-8"))
            if total > self.policy.max_arg_bytes:
                raise ShellPolicyError("command arguments exceed byte limit")
            argv.append(arg)
        return argv

    def _env(self, command: ShellCommand) -> dict[str, str]:
        env: dict[str, str] = {}
        for key in self.policy.inherited_env:
            value = os.environ.get(key)
            if value is not None:
                env[key] = value
        for key, value in command.env.items():
            if key not in self.policy.allowed_env:
                raise ShellPolicyError("command environment key is not allowed")
            if not isinstance(value, str) or "\x00" in value:
                raise ShellPolicyError("command environment values must be NUL-free strings")
            env[key] = value
        total_bytes = sum(len(key.encode("utf-8")) + len(value.encode("utf-8")) + 2 for key, value in env.items())
        if total_bytes > self.policy.max_env_bytes:
            raise ShellPolicyError("command environment exceeds byte limit")
        return env

    def _timeout(self, command: ShellCommand) -> float:
        timeout = self.policy.default_timeout if command.timeout is None else float(command.timeout)
        if timeout <= 0 or timeout > self.policy.max_timeout:
            raise ShellPolicyError("command timeout is outside policy bounds")
        return timeout

    def _stdin(self, command: ShellCommand) -> bytes | None:
        if command.stdin is None:
            return None
        if not isinstance(command.stdin, bytes):
            raise ShellPolicyError("stdin must be bytes")
        if len(command.stdin) > self.policy.max_input_bytes:
            raise ShellPolicyError("stdin exceeds byte limit")
        return command.stdin

    @staticmethod
    def _terminate(proc: subprocess.Popen[bytes]) -> None:
        if proc.poll() is not None:
            return
        try:
            if os.name == "posix":
                os.killpg(proc.pid, signal.SIGTERM)
            else:
                proc.terminate()
        except (ProcessLookupError, PermissionError, OSError):
            try:
                proc.terminate()
            except OSError:
                pass
        try:
            proc.wait(timeout=0.25)
            return
        except subprocess.TimeoutExpired:
            pass
        try:
            if os.name == "posix":
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
        except (ProcessLookupError, PermissionError, OSError):
            try:
                proc.kill()
            except OSError:
                pass
        try:
            proc.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            pass

    def run(self, command: ShellCommand) -> ShellResult:
        argv = self._argv(command)
        cwd = self._cwd(command.cwd)
        env = self._env(command)
        timeout = self._timeout(command)
        stdin_data = self._stdin(command)

        proc = subprocess.Popen(
            argv,
            cwd=str(cwd),
            env=env,
            stdin=subprocess.PIPE if stdin_data is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            close_fds=True,
            start_new_session=(os.name == "posix"),
        )
        assert proc.stdout is not None and proc.stderr is not None

        stdout = bytearray()
        stderr = bytearray()
        remaining = [self.policy.max_output_bytes]
        budget_lock = threading.Lock()
        output_limited = threading.Event()

        def drain(stream, sink: bytearray) -> None:
            try:
                while True:
                    chunk = stream.read(_READ_CHUNK)
                    if not chunk:
                        return
                    with budget_lock:
                        take = min(len(chunk), remaining[0])
                        if take:
                            sink.extend(chunk[:take])
                            remaining[0] -= take
                        if take < len(chunk):
                            output_limited.set()
            except (OSError, ValueError):
                return

        readers = [
            threading.Thread(target=drain, args=(proc.stdout, stdout), daemon=True),
            threading.Thread(target=drain, args=(proc.stderr, stderr), daemon=True),
        ]
        for reader in readers:
            reader.start()

        writer: threading.Thread | None = None
        if stdin_data is not None:
            assert proc.stdin is not None

            def feed() -> None:
                try:
                    proc.stdin.write(stdin_data)
                    proc.stdin.flush()
                except (BrokenPipeError, OSError, ValueError):
                    pass
                finally:
                    try:
                        proc.stdin.close()
                    except (OSError, ValueError):
                        pass

            writer = threading.Thread(target=feed, daemon=True)
            writer.start()

        timed_out = False
        deadline = time.monotonic() + timeout
        while proc.poll() is None:
            if output_limited.is_set():
                self._terminate(proc)
                break
            remaining_time = deadline - time.monotonic()
            if remaining_time <= 0:
                timed_out = True
                self._terminate(proc)
                break
            time.sleep(min(0.01, remaining_time))

        if proc.poll() is None:
            self._terminate(proc)
        if writer is not None:
            writer.join(timeout=0.2)
        for reader in readers:
            reader.join(timeout=0.5)
        for stream in (proc.stdout, proc.stderr):
            try:
                stream.close()
            except (OSError, ValueError):
                pass

        return ShellResult(
            command=command.command,
            returncode=proc.returncode,
            stdout=bytes(stdout),
            stderr=bytes(stderr),
            timed_out=timed_out,
            output_limited=output_limited.is_set(),
            accepted=(proc.returncode in command.allowed_returncodes),
        )

    def run_checked(self, command: ShellCommand) -> ShellResult:
        result = self.run(command)
        if result.timed_out or result.output_limited or result.returncode not in command.allowed_returncodes:
            raise ShellExecutionError(result)
        return result
