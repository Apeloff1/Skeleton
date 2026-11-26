"""Fail-closed readiness for recovered systems.

A system is served only while its probe says it is ready. Probes are plain
callables returning :class:`ProbeResult` (or raising); results are cached
for ``ttl_s`` so the hot path never runs a probe per request, and a cached
result older than ``stale_after_s`` counts as *not ready*. Becoming ready
needs ``rise`` consecutive passes and dropping out needs ``fall``
consecutive failures, so one flaky probe cannot flap the gate. A system
with no registered probe is not ready (fail closed) unless its profile
says ``requires_ready=False``.

Built-in probes:

* :class:`HiveSelfCheckProbe` runs ``skeleton.automation.hive.verify.run_all``.
* :class:`ReceiptProbe` reads a JSON receipt (e.g. the local-model
  provisioning receipt) and checks schema + required keys.
* :class:`LoopbackHttpProbe` GETs a health path on a loopback-only host.
"""

from __future__ import annotations

import http.client
import ipaddress
import json
import os
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple

from skeleton.gate_plane.s2s.clock import Clock, system_clock


@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    reason: str = ""
    detail: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def passed(cls, reason: str = "ok", **detail: Any) -> "ProbeResult":
        return cls(True, reason, detail)

    @classmethod
    def failed(cls, reason: str, **detail: Any) -> "ProbeResult":
        return cls(False, reason or "failed", detail)


Probe = Callable[[], ProbeResult]


@dataclass(frozen=True)
class ReadinessState:
    system: str
    ready: bool
    reason: str
    checked_at: Optional[float]
    passes: int
    failures: int
    probes_run: int

    def as_dict(self) -> Dict[str, Any]:
        return {
            "system": self.system, "ready": self.ready, "reason": self.reason, "checked_at": self.checked_at,
            "passes": self.passes, "failures": self.failures, "probes_run": self.probes_run,
        }


class _Entry:
    __slots__ = ("probe", "ready", "reason", "checked_at", "passes", "failures", "runs", "lock")

    def __init__(self, probe: Probe) -> None:
        self.probe = probe
        self.ready = False
        self.reason = "never_checked"
        self.checked_at: Optional[float] = None
        self.passes = 0
        self.failures = 0
        self.runs = 0
        self.lock = threading.Lock()


class ReadinessRegistry:
    """Per-system probe cache with rise/fall hysteresis."""

    def __init__(
        self,
        *,
        clock: Optional[Clock] = None,
        ttl_s: float = 5.0,
        stale_after_s: float = 60.0,
        rise: int = 1,
        fall: int = 1,
    ) -> None:
        if ttl_s <= 0 or stale_after_s < ttl_s:
            raise ValueError("need 0 < ttl_s <= stale_after_s")
        if rise < 1 or fall < 1:
            raise ValueError("rise and fall must be >= 1")
        self.clock: Clock = clock if clock is not None else system_clock()
        self.ttl_s = float(ttl_s)
        self.stale_after_s = float(stale_after_s)
        self.rise = int(rise)
        self.fall = int(fall)
        self._entries: Dict[str, _Entry] = {}
        self._optional: set[str] = set()
        self._lock = threading.Lock()

    def register(self, system: str, probe: Probe) -> None:
        if not callable(probe):
            raise TypeError("probe must be callable")
        with self._lock:
            if system in self._entries:
                raise ValueError(f"probe already registered for {system!r}")
            self._entries[system] = _Entry(probe)

    def mark_optional(self, system: str) -> None:
        """System whose profile does not require readiness (always admitted)."""
        with self._lock:
            self._optional.add(system)

    def systems(self) -> List[str]:
        with self._lock:
            return sorted(set(self._entries) | self._optional)

    def _run(self, system: str, entry: _Entry, now: float) -> None:
        try:
            res = entry.probe()
            if not isinstance(res, ProbeResult):
                res = ProbeResult.failed("probe_returned_non_result")
        except Exception as exc:  # noqa: BLE001 - any probe error is a failure
            res = ProbeResult.failed("probe_error", error=type(exc).__name__)
        entry.runs += 1
        entry.checked_at = now
        if res.ok:
            entry.passes += 1
            entry.failures = 0
            if not entry.ready and entry.passes >= self.rise:
                entry.ready = True
            entry.reason = res.reason or "ok"
        else:
            entry.failures += 1
            entry.passes = 0
            if entry.ready and entry.failures >= self.fall:
                entry.ready = False
            elif not entry.ready:
                entry.ready = False
            entry.reason = res.reason

    def check(self, system: str, *, force: bool = False) -> ReadinessState:
        with self._lock:
            entry = self._entries.get(system)
            optional = system in self._optional
        if entry is None:
            if optional:
                return ReadinessState(system, True, "readiness_not_required", None, 0, 0, 0)
            return ReadinessState(system, False, "no_probe_registered", None, 0, 0, 0)
        now = self.clock.monotonic()
        with entry.lock:
            due = force or entry.checked_at is None or now - entry.checked_at >= self.ttl_s
            if due:
                self._run(system, entry, now)
            ready = entry.ready
            reason = entry.reason
            if entry.checked_at is not None and now - entry.checked_at > self.stale_after_s:
                ready, reason = False, "stale"
            if optional:
                ready = True
            return ReadinessState(system, ready, reason, entry.checked_at, entry.passes, entry.failures, entry.runs)

    def is_ready(self, system: str) -> bool:
        return self.check(system).ready

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        return {s: self.check(s).as_dict() for s in self.systems()}


class HiveSelfCheckProbe:
    """Ready when Hive 1.0's own acceptance checks all pass (in-process, no I/O)."""

    def __init__(self, runner: Optional[Callable[[], Mapping[str, Any]]] = None) -> None:
        if runner is None:
            from skeleton.automation.hive.verify import run_all

            runner = run_all
        self.runner = runner

    def __call__(self) -> ProbeResult:
        out = self.runner()
        if not isinstance(out, Mapping):
            return ProbeResult.failed("hive_bad_report")
        failed = list(out.get("failed") or [])
        if int(out.get("ok", 0)) == 1 and not failed:
            return ProbeResult.passed("hive_ok", checks=int(out.get("n", 0)))
        return ProbeResult.failed("hive_checks_failed", failed=failed)


class ReceiptProbe:
    """Ready when a JSON receipt exists, parses, has ``schema`` and required keys.

    ``max_bytes`` bounds the read so a corrupted or hostile file cannot stall
    the probe. Symlinked receipts are refused (custody: the receipt must be
    the file the provisioner wrote).
    """

    def __init__(
        self,
        path: str,
        *,
        schema: Optional[str] = None,
        required_keys: Iterable[str] = (),
        max_bytes: int = 256 * 1024,
        validator: Optional[Callable[[Mapping[str, Any]], Optional[str]]] = None,
    ) -> None:
        self.path = str(path)
        self.schema = schema
        self.required_keys = tuple(required_keys)
        self.max_bytes = int(max_bytes)
        self.validator = validator

    def __call__(self) -> ProbeResult:
        try:
            st = os.lstat(self.path)
        except FileNotFoundError:
            return ProbeResult.failed("receipt_missing")
        except OSError as exc:
            return ProbeResult.failed("receipt_unreadable", error=type(exc).__name__)
        import stat as _stat

        if _stat.S_ISLNK(st.st_mode):
            return ProbeResult.failed("receipt_symlink")
        if not _stat.S_ISREG(st.st_mode):
            return ProbeResult.failed("receipt_not_regular")
        if st.st_size > self.max_bytes:
            return ProbeResult.failed("receipt_too_large", size=st.st_size)
        try:
            with open(self.path, "rb") as fh:
                raw = fh.read(self.max_bytes + 1)
        except OSError as exc:
            return ProbeResult.failed("receipt_unreadable", error=type(exc).__name__)
        if len(raw) > self.max_bytes:
            return ProbeResult.failed("receipt_too_large", size=len(raw))
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return ProbeResult.failed("receipt_not_json")
        if not isinstance(data, dict):
            return ProbeResult.failed("receipt_not_object")
        if self.schema is not None and data.get("schema") != self.schema:
            return ProbeResult.failed("receipt_schema_mismatch")
        missing = [k for k in self.required_keys if k not in data]
        if missing:
            return ProbeResult.failed("receipt_missing_keys", missing=missing)
        if self.validator is not None:
            problem = self.validator(data)
            if problem:
                return ProbeResult.failed(str(problem))
        return ProbeResult.passed("receipt_ok")


LOOPBACK_NAMES = frozenset({"localhost", "localhost.localdomain", "ip6-localhost"})


def is_loopback_host(host: str) -> bool:
    """True only for literal loopback IPs or the fixed localhost names (no DNS)."""
    h = (host or "").strip().lower()
    if h.startswith("[") and h.endswith("]"):
        h = h[1:-1]
    if h in LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False


class LoopbackHttpProbe:
    """GET ``path`` on a loopback host; 2xx within ``timeout_s`` means ready.

    Non-loopback hosts are refused at construction. Redirects are failures
    (http.client never follows them). The body read is bounded.
    """

    def __init__(
        self,
        host: str,
        port: int,
        path: str = "/health",
        *,
        timeout_s: float = 1.0,
        max_body_bytes: int = 64 * 1024,
        expect_json_key: Optional[Tuple[str, Any]] = None,
        connection_factory: Optional[Callable[..., Any]] = None,
    ) -> None:
        if not is_loopback_host(host):
            raise ValueError(f"LoopbackHttpProbe refuses non-loopback host {host!r}")
        if not (0 < int(port) < 65536):
            raise ValueError("port out of range")
        if not path.startswith("/"):
            raise ValueError("path must start with '/'")
        self.host = host
        self.port = int(port)
        self.path = path
        self.timeout_s = float(timeout_s)
        self.max_body_bytes = int(max_body_bytes)
        self.expect_json_key = expect_json_key
        self._factory = connection_factory or http.client.HTTPConnection

    def __call__(self) -> ProbeResult:
        conn = self._factory(self.host, self.port, timeout=self.timeout_s)
        try:
            conn.request("GET", self.path, headers={"accept": "application/json"})
            resp = conn.getresponse()
            body = resp.read(self.max_body_bytes + 1)
            status = int(resp.status)
        except (OSError, http.client.HTTPException) as exc:
            return ProbeResult.failed("probe_unreachable", error=type(exc).__name__)
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
        if len(body) > self.max_body_bytes:
            return ProbeResult.failed("probe_body_too_large")
        if not 200 <= status < 300:
            return ProbeResult.failed("probe_status", status=status)
        if self.expect_json_key is not None:
            key, want = self.expect_json_key
            try:
                data = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return ProbeResult.failed("probe_not_json")
            if not isinstance(data, dict) or data.get(key) != want:
                return ProbeResult.failed("probe_unexpected_body")
        return ProbeResult.passed("probe_ok", status=status)


__all__ = [
    "HiveSelfCheckProbe",
    "LOOPBACK_NAMES",
    "LoopbackHttpProbe",
    "Probe",
    "ProbeResult",
    "ReadinessRegistry",
    "ReadinessState",
    "ReceiptProbe",
    "is_loopback_host",
]
