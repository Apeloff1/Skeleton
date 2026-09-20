"""admit_depth — deepened write admission using Pack A ultra-infra.

Calls root ``admit_write`` after priority resolution, optional decision
cache lookup, and ChaosGovernor observation. Fail-closed. Does not mint
identity or bypass seal/auth.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

from skeleton.api.admit_write import (
    EmergencyReadOnlyError,
    ShedError,
    admit_write,
    get_default_gate,
    get_default_governor,
)
from skeleton.api.pack_a.admit_decision_cache import DecisionCacheFacade
from skeleton.api.pack_a.priority_table import priority_for_path, route_class_for_path
from skeleton.kernel.adaptive_gate import AdaptiveGate
from skeleton.kernel.chaos import ChaosGovernor
from skeleton.kernel.pack_a.metrics import default_meter
from skeleton.kernel.pack_a.tiered_depth import AdmitDecision


class RouteClass(str, Enum):
    OPEN = "open"
    AUTH = "auth"
    FORGE = "forge"
    GAMEFORGE = "gameforge"
    SWARM = "swarm"
    CONTROL = "control"
    BULK = "bulk"
    TELEMETRY = "telemetry"
    DEFAULT = "default"


@dataclass
class AdmitDepthContext:
    method: str
    path: str
    priority: Optional[int] = None
    route_class: Optional[str] = None
    use_decision_cache: bool = True
    idempotency_key: Optional[str] = None


@dataclass
class AdmitDepthResult:
    decision: AdmitDecision
    priority: int
    route_class: str
    cache_hit: bool
    elapsed_s: float

    def as_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision.value,
            "priority": self.priority,
            "route_class": self.route_class,
            "cache_hit": self.cache_hit,
            "elapsed_s": self.elapsed_s,
        }


class PriorityResolver:
    def resolve(self, path: str, explicit: Optional[int] = None) -> tuple[str, int]:
        rc = route_class_for_path(path)
        pr = int(explicit) if explicit is not None else priority_for_path(path)
        return rc, pr


class DeepWriteAdmit:
    """Pack A deepened admit orchestrator."""

    _SAFE = frozenset({"GET", "HEAD", "OPTIONS"})

    def __init__(
        self,
        *,
        gate: Optional[AdaptiveGate] = None,
        governor: Optional[ChaosGovernor] = None,
        decisions: Optional[DecisionCacheFacade] = None,
        resolver: Optional[PriorityResolver] = None,
    ) -> None:
        self.gate = gate
        self.governor = governor
        self.decisions = decisions if decisions is not None else DecisionCacheFacade()
        self.resolver = resolver if resolver is not None else PriorityResolver()
        self.meter = default_meter()

    def admit(self, ctx: AdmitDepthContext) -> AdmitDepthResult:
        started = time.monotonic()
        method = (ctx.method or "GET").upper()
        path = ctx.path or "/"
        if method in self._SAFE:
            elapsed = time.monotonic() - started
            return AdmitDepthResult(
                decision=AdmitDecision.SAFE_METHOD,
                priority=0,
                route_class=ctx.route_class or "default",
                cache_hit=False,
                elapsed_s=elapsed,
            )

        rc, pr = self.resolver.resolve(path, ctx.priority)
        if ctx.route_class:
            rc = ctx.route_class

        cache_hit = False
        if ctx.use_decision_cache:
            rec = self.decisions.lookup(rc, pr, path)
            if rec is not None:
                cache_hit = True
                elapsed = time.monotonic() - started
                self.meter.admit_total.labels(rc, rec.decision.value).inc()
                self.meter.admit_latency.labels(rc).observe(elapsed)
                return AdmitDepthResult(
                    decision=rec.decision,
                    priority=pr,
                    route_class=rc,
                    cache_hit=True,
                    elapsed_s=elapsed,
                )

        decision = AdmitDecision.ADMITTED
        try:
            admit_write(priority=pr, gate=self.gate, governor=self.governor)
            gov = self.governor if self.governor is not None else get_default_governor()
            gov.observe(True)
        except ShedError:
            decision = AdmitDecision.SHED
            self.meter.admit_shed.labels(rc).inc()
            gov = self.governor if self.governor is not None else get_default_governor()
            gov.observe(False)
        except EmergencyReadOnlyError:
            decision = AdmitDecision.EMERGENCY_READ_ONLY
            self.meter.admit_emergency.labels(rc).inc()

        if ctx.use_decision_cache and decision in (
            AdmitDecision.ADMITTED,
            AdmitDecision.SHED,
            AdmitDecision.EMERGENCY_READ_ONLY,
        ):
            # Only cache shed/emergency briefly; admitted uses shorter TTL
            ttl = 0.02 if decision is AdmitDecision.ADMITTED else 0.05
            self.decisions.store(rc, pr, path, decision, ttl_s=ttl)

        elapsed = time.monotonic() - started
        self.meter.admit_total.labels(rc, decision.value).inc()
        self.meter.admit_latency.labels(rc).observe(elapsed)
        if decision is AdmitDecision.SHED:
            raise ShedError("shed", context={"error": "shed", "route_class": rc})
        if decision is AdmitDecision.EMERGENCY_READ_ONLY:
            raise EmergencyReadOnlyError(
                "emergency_read_only",
                context={"error": "emergency_read_only", "route_class": rc},
            )
        return AdmitDepthResult(
            decision=decision,
            priority=pr,
            route_class=rc,
            cache_hit=cache_hit,
            elapsed_s=elapsed,
        )


_DEEP = DeepWriteAdmit()


def default_deep_admit() -> DeepWriteAdmit:
    return _DEEP


def reset_default_deep_admit_for_tests() -> None:
    global _DEEP
    _DEEP = DeepWriteAdmit()


def admit_write_deep(
    *,
    method: str,
    path: str,
    priority: Optional[int] = None,
    use_decision_cache: bool = True,
) -> AdmitDepthResult:
    return default_deep_admit().admit(
        AdmitDepthContext(
            method=method,
            path=path,
            priority=priority,
            use_decision_cache=use_decision_cache,
        )
    )


__all__ = [
    "AdmitDepthContext",
    "AdmitDepthResult",
    "DeepWriteAdmit",
    "PriorityResolver",
    "RouteClass",
    "admit_write_deep",
    "default_deep_admit",
    "reset_default_deep_admit_for_tests",
]
