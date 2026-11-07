"""Fail-closed, dependency-injected first-run service readiness gate.

A successful source check is not device, model, installer or release qualification.
Callers supply actual probes; this module never fabricates a healthy service.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Mapping
import time


class FirstRunGateError(ValueError):
    """Invalid first-run readiness configuration."""


class ServiceState(str, Enum):
    READY = "ready"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


@dataclass(frozen=True)
class ServiceResult:
    name: str
    state: ServiceState
    reason: str
    elapsed_ms: int


@dataclass(frozen=True)
class FirstRunReadiness:
    services: tuple[ServiceResult, ...]
    setup_accessible: bool
    guarded_ai_available: bool
    playable_enabled: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "services": [
                {"name": s.name, "state": s.state.value, "reason": s.reason,
                 "elapsed_ms": s.elapsed_ms}
                for s in self.services
            ],
            "setup_accessible": self.setup_accessible,
            "guarded_ai_available": self.guarded_ai_available,
            "playable_enabled": self.playable_enabled,
            "device_qualified": False,
            "release_ready": False,
        }


SERVICE_ORDER = ("backend", "local_ai", "jeeves", "builder", "game_store")
MAX_REASON = 160
MAX_ELAPSED_MS = 86_400_000


def _safe_clock_ns(clock: Callable[[], int]) -> int | None:
    """A broken clock must never make first-run setup inaccessible."""
    try:
        value = clock()
    except Exception:
        return None
    # bool is an int subclass but is not a timestamp.
    if type(value) is not int or value < 0:
        return None
    return value


def _bounded_reason(value: object) -> str:
    if not isinstance(value, str):
        return "probe-returned-non-string"
    safe = "".join(c for c in value if c.isprintable() and c not in "\r\n")
    return safe[:MAX_REASON] or "unspecified"


def check_first_run(
    probes: Mapping[str, Callable[[], bool]],
    *,
    clock_ns: Callable[[], int] = time.monotonic_ns,
) -> FirstRunReadiness:
    """Execute each named probe once, in dependency order.

    Only the exact boolean True means ready. A missing or raising probe fails
    closed; later dependencies are not called after the first unhealthy probe.
    The setup UI stays available independently of backend health.
    """
    if not isinstance(probes, Mapping):
        raise FirstRunGateError("probes must be a mapping")
    unknown = set(probes).difference(SERVICE_ORDER)
    if unknown:
        raise FirstRunGateError("unknown service probe")
    if not callable(clock_ns):
        raise FirstRunGateError("clock must be callable")
    results: list[ServiceResult] = []
    blocked = False
    for name in SERVICE_ORDER:
        probe = probes.get(name)
        if blocked:
            results.append(ServiceResult(name, ServiceState.UNAVAILABLE,
                                         "dependency-unavailable", 0))
            continue
        if probe is None:
            results.append(ServiceResult(name, ServiceState.UNAVAILABLE,
                                         "probe-missing", 0))
            blocked = True
            continue
        if not callable(probe):
            results.append(ServiceResult(name, ServiceState.FAILED,
                                         "probe-not-callable", 0))
            blocked = True
            continue
        start = _safe_clock_ns(clock_ns)
        try:
            outcome = probe()
            state = ServiceState.READY if outcome is True else ServiceState.UNAVAILABLE
            reason = "probe-passed" if outcome is True else "probe-not-ready"
        except Exception as exc:
            state = ServiceState.FAILED
            # Never expose exception text: it may contain tokens or local paths.
            reason = "probe-raised-" + type(exc).__name__[:48]
        finish = _safe_clock_ns(clock_ns)
        if start is None or finish is None or finish < start:
            # Clock faults are not evidence of a healthy probe. Fail closed.
            state = ServiceState.FAILED
            reason = "probe-clock-unavailable"
            elapsed = 0
        else:
            elapsed = min(MAX_ELAPSED_MS, (finish - start) // 1_000_000)
        results.append(ServiceResult(name, state, _bounded_reason(reason), elapsed))
        if state is not ServiceState.READY:
            blocked = True
    ready = {item.name: item.state is ServiceState.READY for item in results}
    return FirstRunReadiness(
        services=tuple(results),
        setup_accessible=True,
        guarded_ai_available=ready["backend"] and ready["local_ai"],
        playable_enabled=all(ready.values()),
    )
