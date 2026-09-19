"""Health-aware bounded planning across one or more model providers."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable

from skeleton.shells.ai.model_circuit import ModelCircuitOpen, ModelCircuitRegistry
from skeleton.shells.ai.model_port import AIModelPort
from skeleton.shells.ai.planner import AIPlanner, PlanningResult
from skeleton.shells.ai.provider_health import ProviderHealth, ProviderHealthRegistry
from skeleton.shells.ai.rate_limit import AIModelRateLimiter
from skeleton.shells.ai.types import AIIntent


@dataclass(frozen=True)
class PlannerAttempt:
    model_id: str
    status: str
    latency_ms: float
    error_type: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "error_type": self.error_type,
        }


@dataclass(frozen=True)
class ResilientPlanningResult:
    result: PlanningResult
    attempts: tuple[PlannerAttempt, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "result": self.result.to_dict(),
            "attempts": [item.to_dict() for item in self.attempts],
        }


class ResilientAIPlanner:
    """Try provider-specific planners without weakening shell policy.

    Each fallback planner must already point at the same model-visible tool and
    policy surface. Fallback changes who proposes, not what can execute.
    """

    def __init__(
        self,
        planners: tuple[AIPlanner, ...],
        *,
        health: ProviderHealthRegistry | None = None,
        circuits: ModelCircuitRegistry | None = None,
        rate_limiter: AIModelRateLimiter | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not planners:
            raise ValueError("at least one AI planner is required")
        self.planners = tuple(planners)
        self.health = (
            health
            if health is not None
            else ProviderHealthRegistry(clock=clock)
        )
        self.circuits = (
            circuits
            if circuits is not None
            else ModelCircuitRegistry(clock=clock)
        )
        self.rate_limiter = (
            rate_limiter
            if rate_limiter is not None
            else AIModelRateLimiter(clock=clock)
        )
        self._clock = clock

    def ordered(self) -> tuple[AIPlanner, ...]:
        ranked = []
        for index, planner in enumerate(self.planners):
            snapshot = self.health.snapshot(planner.model.model_id)
            penalty = {
                ProviderHealth.HEALTHY: 0,
                ProviderHealth.UNKNOWN: 1,
                ProviderHealth.DEGRADED: 2,
                ProviderHealth.UNHEALTHY: 3,
                ProviderHealth.QUARANTINED: 4,
            }[snapshot.state]
            ranked.append((penalty, snapshot.avg_latency_ms, index, planner))
        ranked.sort(key=lambda item: (item[0], item[1], item[2]))
        return tuple(item[3] for item in ranked)

    def propose(
        self,
        intent: AIIntent,
        *,
        prior_observations: tuple[dict[str, object], ...] = (),
    ) -> ResilientPlanningResult:
        attempts = []
        last_error: BaseException | None = None
        quarantined = {
            planner.model.model_id
            for planner in self.planners
            if self.health.snapshot(planner.model.model_id).state
            is ProviderHealth.QUARANTINED
        }
        for planner in self.planners:
            model_id = planner.model.model_id
            if model_id in quarantined:
                attempts.append(
                    PlannerAttempt(model_id, "quarantined", 0.0)
                )
        for planner in self.ordered():
            model_id = planner.model.model_id
            if model_id in quarantined:
                continue
            try:
                self.circuits.allow(model_id)
            except ModelCircuitOpen as exc:
                attempts.append(
                    PlannerAttempt(model_id, "circuit_open", 0.0, type(exc).__name__)
                )
                last_error = exc
                continue
            decision = self.rate_limiter.inspect(model_id, consume=False)
            if not decision.allowed:
                attempts.append(PlannerAttempt(model_id, "rate_limited", 0.0))
                continue
            self.rate_limiter.require(model_id)
            started = self._clock()
            try:
                result = planner.propose(
                    intent,
                    prior_observations=prior_observations,
                )
            except BaseException as exc:
                latency = max(0.0, (self._clock() - started) * 1000.0)
                self.health.record_failure(
                    model_id,
                    latency_ms=latency,
                    error_type=type(exc).__name__,
                )
                self.circuits.failure(model_id)
                attempts.append(
                    PlannerAttempt(model_id, "failed", latency, type(exc).__name__)
                )
                last_error = exc
                continue
            latency = max(0.0, (self._clock() - started) * 1000.0)
            self.health.record_success(model_id, latency_ms=latency)
            self.circuits.success(model_id)
            attempts.append(PlannerAttempt(model_id, "succeeded", latency))
            return ResilientPlanningResult(result, tuple(attempts))
        if last_error is not None:
            raise RuntimeError("all AI planning providers failed") from last_error
        raise RuntimeError("no AI planning provider was eligible")
