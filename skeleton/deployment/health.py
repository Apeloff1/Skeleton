"""Host-level health, readiness and preflight checks for self-hosting.

The runtime exposes its own in-process probes at ``/api/v1/health/live`` and
``/api/v1/health/ready`` (see :mod:`skeleton.observability.health`). This
module covers the *other side* of that contract — what an operator, a
supervisor or the one-command boot path must verify about the host before
and after the process starts:

* **startup** checks run before launch (port free, data dir writable, disk);
* **liveness** checks prove the interpreter and dependencies are usable;
* **readiness** checks prove the configured state and services are reachable,
  and — against a running instance — that the HTTP probes answer ``up``.

Checks are plain callables wrapped in :class:`HealthCheck`; the
:class:`CheckRegistry` runs them concurrently with per-check timeouts and
rolls results up fail-closed: a *critical* failure fails the report, a
non-critical failure only degrades it.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import socket
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .profile import MEMORY_PATH, SelfHostProfile
from .validation import DISK_FAIL_BYTES, DISK_WARN_BYTES, is_loopback_host, parse_mongo_uri

__all__ = [
    "CheckKind",
    "CheckRegistry",
    "CheckResult",
    "CheckStatus",
    "HealthCheck",
    "HealthReport",
    "Outcome",
    "build_preflight_registry",
    "build_runtime_probe_registry",
    "data_dir_writable_check",
    "disk_space_check",
    "http_probe_check",
    "module_check",
    "port_available_check",
    "python_version_check",
    "sqlite_store_check",
    "tcp_reachable_check",
]

LIVE_PATH = "/api/v1/health/live"
READY_PATH = "/api/v1/health/ready"
REQUIRED_MODULES: Tuple[str, ...] = ("fastapi", "uvicorn", "pydantic", "pydantic_settings")
MIN_PYTHON: Tuple[int, int] = (3, 11)


class CheckKind(str, Enum):
    STARTUP = "startup"
    LIVENESS = "liveness"
    READINESS = "readiness"


class CheckStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


@dataclass(frozen=True)
class Outcome:
    """What a check function returns."""

    status: CheckStatus
    detail: str = ""
    data: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, detail: str = "", **data: Any) -> "Outcome":
        return cls(CheckStatus.PASS, detail, data)

    @classmethod
    def warn(cls, detail: str, **data: Any) -> "Outcome":
        return cls(CheckStatus.WARN, detail, data)

    @classmethod
    def fail(cls, detail: str, **data: Any) -> "Outcome":
        return cls(CheckStatus.FAIL, detail, data)

    @classmethod
    def skip(cls, detail: str, **data: Any) -> "Outcome":
        return cls(CheckStatus.SKIP, detail, data)


CheckFn = Callable[[], Outcome]


@dataclass(frozen=True)
class HealthCheck:
    name: str
    kind: CheckKind
    fn: CheckFn
    critical: bool = True
    timeout_s: float = 5.0
    description: str = ""


@dataclass(frozen=True)
class CheckResult:
    name: str
    kind: CheckKind
    status: CheckStatus
    critical: bool
    detail: str
    duration_ms: float
    data: Mapping[str, Any] = field(default_factory=dict)

    @property
    def blocking(self) -> bool:
        return self.critical and self.status is CheckStatus.FAIL

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind.value,
            "status": self.status.value,
            "critical": self.critical,
            "detail": self.detail,
            "duration_ms": round(self.duration_ms, 3),
            "data": dict(self.data),
        }


@dataclass
class HealthReport:
    results: List[CheckResult]

    @property
    def status(self) -> CheckStatus:
        if any(result.blocking for result in self.results):
            return CheckStatus.FAIL
        if any(result.status in (CheckStatus.WARN, CheckStatus.FAIL) for result in self.results):
            return CheckStatus.WARN
        return CheckStatus.PASS

    @property
    def ok(self) -> bool:
        return self.status is not CheckStatus.FAIL

    def by_kind(self, kind: CheckKind) -> List[CheckResult]:
        return [result for result in self.results if result.kind is kind]

    def kind_ok(self, kind: CheckKind) -> bool:
        return not any(result.blocking for result in self.by_kind(kind))

    def failures(self) -> List[CheckResult]:
        return [result for result in self.results if result.status is CheckStatus.FAIL]

    def exit_code(self) -> int:
        return 0 if self.ok else 1

    def to_dict(self) -> Dict[str, Any]:
        summary: Dict[str, int] = {status.value: 0 for status in CheckStatus}
        for result in self.results:
            summary[result.status.value] += 1
        return {
            "kind": "deployment_health",
            "status": self.status.value,
            "ok": self.ok,
            "summary": summary,
            "kinds": {
                kind.value: self.kind_ok(kind)
                for kind in CheckKind
                if self.by_kind(kind)
            },
            "results": [result.to_dict() for result in self.results],
        }


class CheckRegistry:
    """Ordered collection of checks with concurrent, time-bounded execution."""

    def __init__(self, checks: Iterable[HealthCheck] = (), *, clock: Callable[[], float] = time.monotonic) -> None:
        self._checks: List[HealthCheck] = []
        self._clock = clock
        for check in checks:
            self.register(check)

    def register(self, check: HealthCheck) -> HealthCheck:
        if any(existing.name == check.name for existing in self._checks):
            raise ValueError(f"duplicate check name {check.name!r}")
        if check.timeout_s <= 0:
            raise ValueError("check timeout must be positive")
        self._checks.append(check)
        return check

    def add(self, name: str, kind: CheckKind, fn: CheckFn, **kwargs: Any) -> HealthCheck:
        return self.register(HealthCheck(name=name, kind=kind, fn=fn, **kwargs))

    def names(self) -> List[str]:
        return [check.name for check in self._checks]

    def checks(self, kinds: Optional[Sequence[CheckKind]] = None) -> List[HealthCheck]:
        if not kinds:
            return list(self._checks)
        wanted = set(kinds)
        return [check for check in self._checks if check.kind in wanted]

    def _execute(self, check: HealthCheck) -> Tuple[Outcome, float]:
        started = self._clock()
        try:
            outcome = check.fn()
            if not isinstance(outcome, Outcome):
                outcome = Outcome.fail(f"check returned {type(outcome).__name__}, expected Outcome")
        except Exception as exc:  # noqa: BLE001 - a crashing check is a failed check
            outcome = Outcome.fail(f"{type(exc).__name__}: {exc}")
        return outcome, (self._clock() - started) * 1000.0

    def run(self, kinds: Optional[Sequence[CheckKind]] = None) -> HealthReport:
        """Run the selected checks concurrently.

        Each check runs on its own daemon thread and gets ``timeout_s``
        measured from its own start, so a hung check is reported as failed,
        cannot starve other checks and never blocks interpreter exit.
        """

        selected = self.checks(kinds)
        if not selected:
            return HealthReport([])
        boxes: Dict[str, List[Any]] = {}
        threads: Dict[str, Tuple[threading.Thread, float]] = {}

        def worker(check: HealthCheck, box: List[Any]) -> None:
            box.append(self._execute(check))

        for check in selected:
            box: List[Any] = []
            thread = threading.Thread(target=worker, args=(check, box), daemon=True,
                                      name=f"skeleton-deploy-check:{check.name}")
            boxes[check.name] = box
            thread.start()
            threads[check.name] = (thread, time.monotonic() + check.timeout_s)
        results: List[CheckResult] = []
        for check in selected:
            thread, deadline = threads[check.name]
            thread.join(max(0.0, deadline - time.monotonic()))
            box = boxes[check.name]
            if box:
                outcome, elapsed = box[0]
            else:
                outcome, elapsed = Outcome.fail(f"timed out after {check.timeout_s:g}s"), check.timeout_s * 1000.0
            results.append(CheckResult(
                name=check.name,
                kind=check.kind,
                status=outcome.status,
                critical=check.critical,
                detail=outcome.detail,
                duration_ms=elapsed,
                data=dict(outcome.data),
            ))
        return HealthReport(results)


# ---------------------------------------------------------------- factories
def python_version_check(minimum: Tuple[int, int] = MIN_PYTHON, *, version: Optional[Tuple[int, ...]] = None) -> CheckFn:
    def run() -> Outcome:
        current = tuple(version or sys.version_info[:3])
        label = ".".join(str(part) for part in current)
        if current[:2] < minimum:
            return Outcome.fail(f"python {label} < required {minimum[0]}.{minimum[1]}", version=label)
        return Outcome.ok(f"python {label}", version=label)

    return run


def module_check(modules: Sequence[str] = REQUIRED_MODULES,
                 *, finder: Callable[[str], Any] = importlib.util.find_spec) -> CheckFn:
    def run() -> Outcome:
        missing = []
        for name in modules:
            try:
                if finder(name) is None:
                    missing.append(name)
            except (ImportError, ValueError):
                missing.append(name)
        if missing:
            return Outcome.fail(f"missing modules: {', '.join(missing)}", missing=missing)
        return Outcome.ok(f"{len(modules)} modules importable", modules=list(modules))

    return run


def _nearest_existing(path: Path) -> Path:
    current = path
    while not current.exists() and current.parent != current:
        current = current.parent
    return current


def data_dir_writable_check(path: Optional[Path], *, create: bool = False) -> CheckFn:
    def run() -> Outcome:
        if path is None:
            return Outcome.skip("no data_dir (in-memory stores)")
        if path.exists() and not path.is_dir():
            return Outcome.fail(f"{path} is not a directory")
        if not path.exists():
            if create:
                path.mkdir(parents=True, exist_ok=True, mode=0o750)
            else:
                anchor = _nearest_existing(path)
                if os.access(anchor, os.W_OK | os.X_OK):
                    return Outcome.ok(f"{path} will be created under {anchor}", created=False)
                return Outcome.fail(f"{path} does not exist and {anchor} is not writable")
        try:
            with tempfile.NamedTemporaryFile(dir=path, prefix=".skeleton-probe-", delete=True) as handle:
                handle.write(b"ok")
                handle.flush()
        except OSError as exc:
            return Outcome.fail(f"{path} is not writable: {exc.strerror or exc}")
        return Outcome.ok(f"{path} is writable")

    return run


def disk_space_check(path: Optional[Path], *, warn_bytes: int = DISK_WARN_BYTES, fail_bytes: int = DISK_FAIL_BYTES,
                     usage: Callable[[str], Any] = shutil.disk_usage) -> CheckFn:
    def run() -> Outcome:
        if path is None:
            return Outcome.skip("no data_dir (in-memory stores)")
        anchor = _nearest_existing(path)
        try:
            free = int(usage(str(anchor)).free)
        except OSError as exc:
            return Outcome.warn(f"cannot stat {anchor}: {exc.strerror or exc}")
        mib = free // (1024 * 1024)
        if free < fail_bytes:
            return Outcome.fail(f"{mib} MiB free under {anchor}", free_bytes=free)
        if free < warn_bytes:
            return Outcome.warn(f"{mib} MiB free under {anchor}", free_bytes=free)
        return Outcome.ok(f"{mib} MiB free under {anchor}", free_bytes=free)

    return run


def sqlite_store_check(name: str, path: str) -> CheckFn:
    """Verify an existing SQLite store is intact, or that it can be created."""

    def run() -> Outcome:
        if path == MEMORY_PATH:
            return Outcome.skip(f"{name} is in-memory")
        file_path = Path(os.path.expanduser(path))
        if not file_path.exists():
            anchor = _nearest_existing(file_path.parent)
            if os.access(anchor, os.W_OK | os.X_OK):
                return Outcome.ok(f"{name} will be created at {file_path}", exists=False)
            return Outcome.fail(f"{name}: cannot create {file_path} ({anchor} not writable)", exists=False)
        if not file_path.is_file():
            return Outcome.fail(f"{name}: {file_path} is not a regular file")
        try:
            uri = f"{file_path.resolve().as_uri()}?mode=ro"
            connection = sqlite3.connect(uri, uri=True, timeout=2.0)
            try:
                row = connection.execute("PRAGMA quick_check").fetchone()
            finally:
                connection.close()
        except sqlite3.DatabaseError as exc:
            return Outcome.fail(f"{name}: {file_path} is not a usable SQLite database: {exc}")
        verdict = row[0] if row else "no result"
        if verdict != "ok":
            return Outcome.fail(f"{name}: quick_check reported {verdict!r}", exists=True)
        return Outcome.ok(f"{name}: {file_path} ok", exists=True, bytes=file_path.stat().st_size)

    return run


def port_available_check(host: str, port: int) -> CheckFn:
    def run() -> Outcome:
        bind_host = host.strip("[]") or "0.0.0.0"
        family = socket.AF_INET6 if ":" in bind_host else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_STREAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((bind_host, port))
        except OSError as exc:
            return Outcome.fail(f"cannot bind {bind_host}:{port}: {exc.strerror or exc}", port=port)
        finally:
            sock.close()
        return Outcome.ok(f"{bind_host}:{port} is free", port=port)

    return run


def tcp_reachable_check(label: str, endpoints: Sequence[Tuple[str, int]], *, timeout_s: float = 2.0,
                        connector: Callable[..., Any] = socket.create_connection) -> CheckFn:
    """Pass when at least one endpoint accepts a TCP connection."""

    def run() -> Outcome:
        errors = []
        for host, port in endpoints:
            try:
                connection = connector((host, port), timeout=timeout_s)
            except OSError as exc:
                errors.append(f"{host}:{port} {exc.strerror or exc}")
                continue
            try:
                connection.close()
            except OSError:
                pass
            return Outcome.ok(f"{label} reachable at {host}:{port}", endpoint=f"{host}:{port}")
        return Outcome.fail(f"{label} unreachable: {'; '.join(errors)}", errors=errors)

    return run


def _default_fetch(url: str, timeout_s: float) -> Tuple[int, bytes]:
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"refusing non-HTTP probe URL {url!r}")
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "skeleton-deploy-probe"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:  # noqa: S310 - scheme checked above
            return int(response.status), response.read(1024 * 1024)
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read(1024 * 1024) if exc.fp else b""


def interpret_probe_body(status_code: int, body: bytes) -> Outcome:
    """Map an HTTP probe response onto a check outcome.

    ``200`` with a JSON body whose ``status`` is ``down``/``unhealthy`` (the
    runtime's observability registry shape) is a failure, as is any non-2xx
    response; a non-JSON ``200`` passes with a warning.
    """

    if not 200 <= status_code < 300:
        return Outcome.fail(f"HTTP {status_code}", http_status=status_code)
    try:
        payload = json.loads(body.decode("utf-8") or "null")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return Outcome.warn(f"HTTP {status_code} with non-JSON body", http_status=status_code)
    if isinstance(payload, dict):
        reported = str(payload.get("status", "")).lower()
        if reported in ("down", "unhealthy", "fail", "failed"):
            failing = [p.get("name") for p in payload.get("probes", []) if isinstance(p, dict) and not p.get("ok", True)]
            return Outcome.fail(f"service reports {reported}", http_status=status_code, failing=failing)
        if reported == "degraded":
            return Outcome.warn("service reports degraded", http_status=status_code)
        if payload.get("ready") is False:
            return Outcome.fail("service reports ready=false", http_status=status_code)
    return Outcome.ok(f"HTTP {status_code}", http_status=status_code)


def http_probe_check(url: str, *, timeout_s: float = 3.0,
                     fetch: Callable[[str, float], Tuple[int, bytes]] = _default_fetch) -> CheckFn:
    def run() -> Outcome:
        try:
            status_code, body = fetch(url, timeout_s)
        except (OSError, ValueError) as exc:
            reason = getattr(exc, "reason", None) or exc
            return Outcome.fail(f"{url} unreachable: {reason}")
        return interpret_probe_body(status_code, body)

    return run


# ------------------------------------------------------------- assemblies
def build_preflight_registry(
    profile: SelfHostProfile,
    *,
    include_network: bool = True,
    include_port: bool = True,
    connector: Callable[..., Any] = socket.create_connection,
) -> CheckRegistry:
    """Assemble the host checks that gate ``deploy boot`` for ``profile``."""

    registry = CheckRegistry()
    root = profile.data_path()
    registry.add("python", CheckKind.LIVENESS, python_version_check(), description="interpreter version")
    registry.add("modules", CheckKind.LIVENESS, module_check(), description="runtime dependencies importable")
    if include_port:
        registry.add("port", CheckKind.STARTUP, port_available_check(profile.host, profile.port),
                     description="bind address is free")
    registry.add("data_dir", CheckKind.STARTUP, data_dir_writable_check(root), description="data dir writable")
    registry.add("disk", CheckKind.STARTUP, disk_space_check(root), description="free disk under data dir")
    for key, path in profile.store_paths().items():
        registry.add(f"store.{key}", CheckKind.READINESS, sqlite_store_check(key, path),
                     description=f"{key} SQLite store")
    if include_network and profile.mongo_uri:
        try:
            scheme, hosts, _creds = parse_mongo_uri(profile.mongo_uri)
        except ValueError as exc:
            message = f"invalid Mongo URI: {exc}"
            registry.add("mongo", CheckKind.READINESS, lambda: Outcome.fail(message))
        else:
            if scheme == "mongodb+srv":
                registry.add("mongo", CheckKind.READINESS,
                             lambda: Outcome.skip("mongodb+srv seed lists resolve via DNS SRV at runtime"),
                             critical=False)
            else:
                registry.add("mongo", CheckKind.READINESS,
                             tcp_reachable_check("mongo", hosts, connector=connector),
                             critical=profile.is_production, description="canonical memory Mongo")
    if include_network and profile.chroma_persist is False and not is_loopback_host(profile.chroma_host):
        registry.add("chroma", CheckKind.READINESS,
                     tcp_reachable_check("chroma", [(profile.chroma_host, profile.chroma_port)], connector=connector),
                     critical=False, description="remote Chroma vector store")
    return registry


def build_runtime_probe_registry(
    base_url: str,
    *,
    timeout_s: float = 3.0,
    fetch: Callable[[str, float], Tuple[int, bytes]] = _default_fetch,
) -> CheckRegistry:
    """Checks against a *running* instance's HTTP liveness/readiness probes."""

    base = base_url.rstrip("/")
    registry = CheckRegistry()
    registry.add("http.live", CheckKind.LIVENESS, http_probe_check(base + LIVE_PATH, timeout_s=timeout_s, fetch=fetch),
                 timeout_s=timeout_s + 1.0, description="GET " + LIVE_PATH)
    registry.add("http.ready", CheckKind.READINESS,
                 http_probe_check(base + READY_PATH, timeout_s=timeout_s, fetch=fetch),
                 timeout_s=timeout_s + 1.0, description="GET " + READY_PATH)
    return registry
