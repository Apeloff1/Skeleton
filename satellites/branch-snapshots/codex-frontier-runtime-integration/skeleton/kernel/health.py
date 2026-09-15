"""Health rollup — one readiness/liveness answer for the whole kernel.

Watchdogs, supervisors, breakers, and governors each know their own
corner of the world, but the API boundary and the operator dashboard
need a single answer: *is this kernel ready to take work, and if not,
why?* This module aggregates named health probes into that answer.

- :class:`Probe` — a named check returning OK / DEGRADED / FAILED plus
  an optional detail string; probes can be marked critical (liveness)
  or advisory (readiness-only).
- :class:`HealthRegistry` — runs probes with individual timeouts,
  caches results for a TTL so a chatty health endpoint can't stampede
  the subsystems, and rolls everything up: any critical FAILED →
  UNHEALTHY, any DEGRADED → DEGRADED, else HEALTHY.
- The rollup is deterministic: probes evaluated in registration order,
  first failure wins the headline slot.

Zero deps, injectable clock; the actual probe functions are owned by
the subsystems they measure.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

from .errors import KernelError


class HealthError(KernelError):
    code = "KRN.HEALTH"


class ProbeStatus(str, Enum):
    OK = "OK"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


class Rollup(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"


@dataclass(frozen=True)
class ProbeResult:
    status: ProbeStatus
    detail: str = ""


@dataclass(frozen=True)
class ProbeReport:
    name: str
    critical: bool
    result: ProbeResult
    duration_s: float


@dataclass
class _Probe:
    name: str
    check: Callable[[], ProbeResult]
    critical: bool
    cached: Optional[ProbeReport] = None
    cached_at: float = 0.0


class HealthRegistry:
    """Registry + rollup. One per kernel; the API layer reads report()."""

    def __init__(self, *, cache_ttl_s: float = 2.0,
                 probe_timeout_s: float = 1.0,
                 clock: Optional[Callable[[], float]] = None) -> None:
        if cache_ttl_s < 0 or probe_timeout_s <= 0:
            raise HealthError(
                "probe timing bounds invalid",
                context={"cache_ttl": cache_ttl_s, "timeout": probe_timeout_s},
            )
        self.cache_ttl_s = cache_ttl_s
        self.probe_timeout_s = probe_timeout_s
        self._now = clock or time.monotonic
        self._probes: Dict[str, _Probe] = {}

    def register(self, name: str, check: Callable[[], ProbeResult],
                 *, critical: bool = True) -> None:
        if name in self._probes:
            raise HealthError("probe already registered",
                              context={"probe": name})
        self._probes[name] = _Probe(name, check, critical)

    def deregister(self, name: str) -> bool:
        return self._probes.pop(name, None) is not None

    def invalidate(self, name: Optional[str] = None) -> None:
        """Force fresh probe runs on next report (e.g. after a config change)."""
        for probe in self._probes.values():
            if name is None or probe.name == name:
                probe.cached = None

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def _run(self, probe: _Probe) -> ProbeReport:
        now = self._now()
        if (probe.cached is not None
                and now - probe.cached_at < self.cache_ttl_s):
            return probe.cached
        start = self._now()
        try:
            result = probe.check()
        except Exception as exc:
            result = ProbeResult(ProbeStatus.FAILED, f"probe raised: {exc!r}")
        duration = self._now() - start
        if duration > self.probe_timeout_s and result.status is ProbeStatus.OK:
            result = ProbeResult(ProbeStatus.DEGRADED,
                                 f"probe slow: {duration:.3f}s")
        report = ProbeReport(probe.name, probe.critical, result, duration)
        probe.cached = report
        probe.cached_at = self._now()
        return report

    def report(self) -> Dict[str, object]:
        reports = [self._run(p) for p in self._probes.values()]
        rollup = Rollup.HEALTHY
        headline = "all probes OK"
        for rep in reports:
            if rep.result.status is ProbeStatus.FAILED and rep.critical:
                rollup = Rollup.UNHEALTHY
                headline = f"{rep.name}: {rep.result.detail or 'FAILED'}"
                break
            if rep.result.status is not ProbeStatus.OK and rollup is Rollup.HEALTHY:
                rollup = Rollup.DEGRADED
                headline = f"{rep.name}: {rep.result.detail or rep.result.status.value}"
        return {
            "status": rollup.value,
            "headline": headline,
            "probes": [
                {
                    "name": r.name,
                    "critical": r.critical,
                    "status": r.result.status.value,
                    "detail": r.result.detail,
                    "duration_s": round(r.duration_s, 4),
                }
                for r in reports
            ],
        }

    def liveness(self) -> bool:
        """Cheap boolean for /livez: no critical probe FAILED."""
        return self.report()["status"] != Rollup.UNHEALTHY.value

    def probes(self) -> Tuple[str, ...]:
        return tuple(sorted(self._probes))
