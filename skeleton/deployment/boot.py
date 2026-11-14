"""One-command local boot for a self-hosted Skeleton.

``python -m skeleton deploy boot`` resolves a profile and walks a fixed,
fail-closed sequence of steps:

``resolve → token → validate → prepare → env_file → preflight → launch → ready → serve``

* nothing is launched unless validation and the critical preflight checks
  pass;
* the child process gets an environment derived *only* from the profile (any
  inherited ``SKL_*`` variable is dropped, and provider credentials are
  stripped for ``offline`` profiles), so what was validated is what runs;
* readiness is proven against the live HTTP probes, and a process that does
  not become ready within the timeout is stopped rather than left half-up.

Every side effect (process launch, HTTP probe, sleep, clock) is injectable,
which is how the test-suite drives the full sequence without sockets.
"""

from __future__ import annotations

import os
import secrets
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol, Sequence, Tuple

from .envfile import write_env_file
from .health import CheckKind, CheckStatus, build_preflight_registry, build_runtime_probe_registry
from .profile import MANAGED_ENV, MEMORY_PATH, PROVIDER_KEY_ENV, SelfHostProfile
from .units import server_argv, shell_command
from .validation import validate_profile

__all__ = [
    "BOOT_STEPS",
    "BootOptions",
    "BootResult",
    "BootStep",
    "Booter",
    "ProcessHandle",
    "StepStatus",
    "boot",
    "child_environment",
    "default_launcher",
    "stop_process",
]

BOOT_STEPS: Tuple[str, ...] = (
    "resolve", "token", "validate", "prepare", "env_file", "preflight", "launch", "ready", "serve",
)
TOKEN_BYTES = 48


class StepStatus(str, Enum):
    OK = "ok"
    WARN = "warn"
    PLANNED = "planned"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True)
class BootStep:
    name: str
    status: StepStatus
    detail: str = ""
    data: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "status": self.status.value, "detail": self.detail, "data": dict(self.data)}


@dataclass
class BootResult:
    profile: str
    fingerprint: str
    url: str
    dry_run: bool
    steps: List[BootStep] = field(default_factory=list)
    pid: Optional[int] = None
    returncode: Optional[int] = None

    @property
    def ok(self) -> bool:
        if any(step.status is StepStatus.FAILED for step in self.steps):
            return False
        return self.returncode in (None, 0) or self.returncode == -signal.SIGTERM

    @property
    def failed_step(self) -> Optional[str]:
        for step in self.steps:
            if step.status is StepStatus.FAILED:
                return step.name
        return None

    def step(self, name: str) -> Optional[BootStep]:
        for item in self.steps:
            if item.name == name:
                return item
        return None

    def exit_code(self) -> int:
        if self.ok:
            return 0
        if self.failed_step in ("validate", "token"):
            return 2
        return 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": "deployment_boot",
            "profile": self.profile,
            "fingerprint": self.fingerprint,
            "url": self.url,
            "dry_run": self.dry_run,
            "ok": self.ok,
            "failed_step": self.failed_step,
            "pid": self.pid,
            "returncode": self.returncode,
            "steps": [step.to_dict() for step in self.steps],
        }


class ProcessHandle(Protocol):
    pid: int

    def poll(self) -> Optional[int]: ...

    def wait(self, timeout: Optional[float] = None) -> int: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...


Launcher = Callable[[Sequence[str], Mapping[str, str], Optional[str], Optional[str]], ProcessHandle]
Fetch = Callable[[str, float], Tuple[int, bytes]]


def default_launcher(argv: Sequence[str], env: Mapping[str, str], cwd: Optional[str],
                     log_path: Optional[str]) -> ProcessHandle:
    """Spawn the server; with ``log_path`` it is detached into its own session."""

    if log_path:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        log = open(log_path, "ab", buffering=0)  # noqa: SIM115 - handed to the child
        try:
            return subprocess.Popen(  # noqa: S603 - argv is built from a validated profile
                list(argv), env=dict(env), cwd=cwd, stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
            )
        finally:
            log.close()
    return subprocess.Popen(list(argv), env=dict(env), cwd=cwd)  # noqa: S603


def stop_process(handle: ProcessHandle, *, grace_s: float = 10.0) -> Optional[int]:
    """SIGTERM, wait ``grace_s``, then SIGKILL. Returns the exit code."""

    if handle.poll() is not None:
        return handle.poll()
    try:
        handle.terminate()
        return handle.wait(timeout=grace_s)
    except subprocess.TimeoutExpired:
        handle.kill()
        try:
            return handle.wait(timeout=grace_s)
        except subprocess.TimeoutExpired:
            return None
    except ProcessLookupError:
        return handle.poll()


def child_environment(profile: SelfHostProfile, base: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    """The exact environment the server process receives for ``profile``."""

    source = dict(os.environ if base is None else base)
    env = {
        key: value
        for key, value in source.items()
        if not key.startswith("SKL_") and key not in MANAGED_ENV
    }
    if profile.offline:
        for key in PROVIDER_KEY_ENV:
            env.pop(key, None)
    env.update(profile.to_env(include_secrets=True))
    env.setdefault("PYTHONUNBUFFERED", "1")
    return env


@dataclass
class BootOptions:
    dry_run: bool = False
    wait_ready: bool = True
    foreground: bool = True
    ready_timeout_s: float = 90.0
    poll_interval_s: float = 0.5
    probe_timeout_s: float = 2.0
    write_env: Optional[str] = None
    generate_token: bool = False
    skip_preflight: bool = False
    check_settings: bool = True
    network_checks: bool = True
    reload: bool = False
    python: str = field(default_factory=lambda: sys.executable or "python3")
    cwd: Optional[str] = None
    log_path: Optional[str] = None
    stop_grace_s: float = 10.0


class Booter:
    """Drives the boot sequence for one profile."""

    def __init__(
        self,
        profile: SelfHostProfile,
        options: Optional[BootOptions] = None,
        *,
        launcher: Launcher = default_launcher,
        fetch: Optional[Fetch] = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        emit: Optional[Callable[[str], None]] = None,
        base_env: Optional[Mapping[str, str]] = None,
    ) -> None:
        self.profile = profile
        self.options = options or BootOptions()
        self._launcher = launcher
        self._fetch = fetch
        self._sleep = sleep
        self._clock = clock
        self._emit = emit or (lambda _line: None)
        self._base_env = base_env
        self.handle: Optional[ProcessHandle] = None

    # ------------------------------------------------------------ helpers
    def _record(self, result: BootResult, name: str, status: StepStatus, detail: str = "", **data: Any) -> BootStep:
        step = BootStep(name, status, detail, data)
        result.steps.append(step)
        self._emit(f"[deploy] {name:<9} {status.value:<7} {detail}".rstrip())
        return step

    def _new_result(self) -> BootResult:
        return BootResult(
            profile=self.profile.name,
            fingerprint=self.profile.fingerprint(),
            url=self.profile.base_url,
            dry_run=self.options.dry_run,
        )

    def argv(self) -> List[str]:
        return server_argv(self.profile, python=self.options.python, reload=self.options.reload)

    def _probe_registry(self):
        kwargs: Dict[str, Any] = {"timeout_s": self.options.probe_timeout_s}
        if self._fetch is not None:
            kwargs["fetch"] = self._fetch
        return build_runtime_probe_registry(self.profile.base_url, **kwargs)

    # -------------------------------------------------------------- steps
    def _step_token(self, result: BootResult) -> bool:
        profile = self.profile
        if profile.service_token:
            self._record(result, "token", StepStatus.OK, "engine service token provided", length=len(profile.service_token))
            return True
        if not self.options.generate_token:
            self._record(result, "token", StepStatus.SKIPPED, "no engine service token (engine routes stay closed)")
            return True
        token = secrets.token_urlsafe(TOKEN_BYTES)
        self.profile = profile.with_overrides(service_token=token)
        result.fingerprint = self.profile.fingerprint()
        persisted = bool(self.options.write_env) and not self.options.dry_run
        detail = (
            f"generated; persisted to {self.options.write_env}" if persisted
            else "generated for this run only (use --write-env to persist it)"
        )
        self._record(result, "token", StepStatus.OK if persisted else StepStatus.WARN, detail, generated=True)
        return True

    def _step_validate(self, result: BootResult) -> bool:
        report = validate_profile(
            self.profile,
            check_filesystem=True,
            check_settings=self.options.check_settings,
        )
        data = {"errors": [i.to_dict() for i in report.errors], "warnings": [i.to_dict() for i in report.warnings]}
        if not report.ok:
            summary = ", ".join(f"{i.code} {i.field}" for i in report.errors)
            self._record(result, "validate", StepStatus.FAILED, f"{len(report.errors)} error(s): {summary}", **data)
            return False
        status = StepStatus.WARN if report.warnings else StepStatus.OK
        self._record(result, "validate", status, f"{len(report.warnings)} warning(s)", **data)
        return True

    def _directories(self) -> List[Path]:
        dirs: List[Path] = []
        root = self.profile.data_path()
        if root is not None:
            dirs.append(root)
        for path in self.profile.store_paths().values():
            if path != MEMORY_PATH:
                parent = Path(os.path.expanduser(path)).parent
                if parent not in dirs:
                    dirs.append(parent)
        persist = self.profile.chroma_persist_directory()
        if persist:
            dirs.append(Path(persist))
        return dirs

    def _step_prepare(self, result: BootResult) -> bool:
        dirs = self._directories()
        if not dirs:
            self._record(result, "prepare", StepStatus.SKIPPED, "in-memory profile; nothing to create")
            return True
        if self.options.dry_run:
            self._record(result, "prepare", StepStatus.PLANNED, f"ensure {len(dirs)} director(ies)",
                         directories=[str(d) for d in dirs])
            return True
        created: List[str] = []
        try:
            for directory in dirs:
                if not directory.exists():
                    directory.mkdir(parents=True, mode=0o750, exist_ok=True)
                    created.append(str(directory))
        except OSError as exc:
            self._record(result, "prepare", StepStatus.FAILED, f"cannot create {exc.filename}: {exc.strerror}")
            return False
        self._record(result, "prepare", StepStatus.OK, f"{len(created)} created, {len(dirs) - len(created)} existing",
                     created=created, directories=[str(d) for d in dirs])
        return True

    def _step_env_file(self, result: BootResult) -> bool:
        target = self.options.write_env
        if not target:
            self._record(result, "env_file", StepStatus.SKIPPED, "no --write-env")
            return True
        if self.options.dry_run:
            self._record(result, "env_file", StepStatus.PLANNED, f"write {target} (0600)")
            return True
        header = (
            f"Skeleton self-host environment — profile {self.profile.name}\n"
            f"fingerprint {self.profile.fingerprint()}\n"
            "Generated by `python -m skeleton deploy`. Contains secrets: keep 0600."
        )
        try:
            write_env_file(target, self.profile.to_env(include_secrets=True), header=header)
        except OSError as exc:
            self._record(result, "env_file", StepStatus.FAILED, f"cannot write {target}: {exc.strerror or exc}")
            return False
        self._record(result, "env_file", StepStatus.OK, f"wrote {target}", path=str(target))
        return True

    def _step_preflight(self, result: BootResult) -> bool:
        if self.options.skip_preflight:
            self._record(result, "preflight", StepStatus.SKIPPED, "--skip-preflight")
            return True
        registry = build_preflight_registry(
            self.profile,
            include_network=self.options.network_checks,
            include_port=True,
        )
        report = registry.run()
        data = {"report": report.to_dict()}
        if not report.ok:
            failed = ", ".join(r.name for r in report.results if r.blocking)
            self._record(result, "preflight", StepStatus.FAILED, f"blocking: {failed}", **data)
            return False
        status = StepStatus.OK if report.status is CheckStatus.PASS else StepStatus.WARN
        self._record(result, "preflight", status, f"{len(report.results)} checks", **data)
        return True

    def _step_launch(self, result: BootResult) -> bool:
        argv = self.argv()
        if self.options.dry_run:
            self._record(result, "launch", StepStatus.PLANNED, shell_command(argv), argv=argv)
            return True
        env = child_environment(self.profile, self._base_env)
        try:
            self.handle = self._launcher(argv, env, self.options.cwd, self.options.log_path)
        except OSError as exc:
            self._record(result, "launch", StepStatus.FAILED, f"cannot start server: {exc.strerror or exc}", argv=argv)
            return False
        result.pid = getattr(self.handle, "pid", None)
        self._record(result, "launch", StepStatus.OK, f"pid {result.pid}: {shell_command(argv)}", argv=argv)
        return True

    def _step_ready(self, result: BootResult) -> bool:
        if self.options.dry_run:
            self._record(result, "ready", StepStatus.PLANNED, f"poll {self.profile.base_url} live+ready")
            return True
        if not self.options.wait_ready:
            self._record(result, "ready", StepStatus.SKIPPED, "--no-wait")
            return True
        assert self.handle is not None
        registry = self._probe_registry()
        deadline = self._clock() + self.options.ready_timeout_s
        attempts = 0
        last_detail = "no probe yet"
        while True:
            code = self.handle.poll()
            if code is not None:
                result.returncode = code
                self._record(result, "ready", StepStatus.FAILED, f"server exited with code {code} before ready",
                             attempts=attempts)
                return False
            attempts += 1
            report = registry.run()
            if report.kind_ok(CheckKind.LIVENESS) and report.kind_ok(CheckKind.READINESS):
                self._record(result, "ready", StepStatus.OK, f"{self.profile.base_url} ready after {attempts} probe(s)",
                             attempts=attempts, report=report.to_dict())
                return True
            failing = report.failures()
            if failing:
                last_detail = "; ".join(f"{r.name}: {r.detail}" for r in failing)
            if self._clock() >= deadline:
                result.returncode = stop_process(self.handle, grace_s=self.options.stop_grace_s)
                self._record(result, "ready", StepStatus.FAILED,
                             f"not ready within {self.options.ready_timeout_s:g}s ({last_detail}); server stopped",
                             attempts=attempts)
                return False
            self._sleep(self.options.poll_interval_s)

    def _step_serve(self, result: BootResult) -> bool:
        if self.options.dry_run:
            self._record(result, "serve", StepStatus.PLANNED, "foreground" if self.options.foreground else "detached")
            return True
        assert self.handle is not None
        if not self.options.foreground:
            self._record(result, "serve", StepStatus.OK, f"detached (pid {result.pid})", detached=True)
            return True
        self._emit(f"[deploy] serving {self.profile.base_url} — Ctrl-C to stop")
        try:
            result.returncode = self.handle.wait()
        except KeyboardInterrupt:
            child_code = stop_process(self.handle, grace_s=self.options.stop_grace_s)
            # An operator-requested stop is a clean exit regardless of how the child reported it.
            result.returncode = 0
            self._record(result, "serve", StepStatus.OK, "stopped by operator", child_returncode=child_code)
            return True
        status = StepStatus.OK if result.returncode == 0 else StepStatus.FAILED
        self._record(result, "serve", status, f"server exited with code {result.returncode}")
        return status is StepStatus.OK

    # ----------------------------------------------------------------- run
    def run(self) -> BootResult:
        self.profile = self.profile.absolutized(self.options.cwd)
        result = self._new_result()
        self._record(result, "resolve", StepStatus.OK, f"profile {self.profile.name} ({self.profile.environment})",
                     profile=self.profile.to_dict(redact=True))
        sequence = (
            self._step_token,
            self._step_validate,
            self._step_prepare,
            self._step_env_file,
            self._step_preflight,
            self._step_launch,
            self._step_ready,
            self._step_serve,
        )
        for step in sequence:
            if not step(result):
                break
        return result

    def plan(self) -> BootResult:
        """Run the sequence without side effects (equivalent to ``dry_run``)."""

        saved = self.options.dry_run
        self.options.dry_run = True
        try:
            return self.run()
        finally:
            self.options.dry_run = saved


def boot(profile: SelfHostProfile, options: Optional[BootOptions] = None, **kwargs: Any) -> BootResult:
    """Convenience wrapper: ``Booter(profile, options, **kwargs).run()``."""

    return Booter(profile, options, **kwargs).run()
