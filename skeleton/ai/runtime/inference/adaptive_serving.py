"""Bounded, disposable load feedback for the existing local inference owner.

This helper has no model, provider, persistence, or execution authority. Its
decisions only reduce an operator's serving ceiling and recover within it.
The inference owner serializes access and supplies monotonic time/resources.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from typing import Any


@dataclass(frozen=True, slots=True)
class AdaptiveServingPolicy:
    enabled: bool = True
    min_effective_concurrency: int = 1
    max_effective_concurrency: int = 1
    target_latency_ms: float = 30_000.0
    cooldown_seconds: float = 5.0
    recovery_samples: int = 4
    max_queue_wait_seconds: float = 30.0
    background_max_concurrency: int = 1
    cache_max_bytes: int = 64 * 1024 * 1024
    cache_ttl_seconds: float = 300.0
    memory_high_watermark: float = 0.90
    memory_low_watermark: float = 0.75
    max_active_per_tenant: int = 1
    max_queued_per_tenant: int = 64
    background_starvation_seconds: float = 5.0
    memory_shed_watermark: float = 0.97

    @classmethod
    def defaults(cls, operator_max: int, operator_queue_max: int = 256) -> AdaptiveServingPolicy:
        return cls(
            max_effective_concurrency=operator_max,
            background_max_concurrency=max(1, operator_max - 1),
            max_active_per_tenant=operator_max,
            max_queued_per_tenant=min(operator_queue_max, max(1, operator_queue_max // 4)),
        )

    def updated(
        self,
        values: Mapping[str, Any],
        operator_max: int,
        operator_queue_max: int = 256,
    ) -> AdaptiveServingPolicy:
        if not isinstance(values, Mapping):
            raise ValueError("serving policy must be an object")
        unknown = set(values) - set(self.__dataclass_fields__)
        if unknown:
            raise ValueError("unknown serving policy fields: " + ", ".join(sorted(map(str, unknown))))
        candidate = replace(self, **dict(values))
        if type(candidate.enabled) is not bool:
            raise ValueError("serving enabled must be boolean")
        for name, lower, upper in (
            ("min_effective_concurrency", 1, operator_max),
            ("max_effective_concurrency", 1, operator_max),
            ("background_max_concurrency", 0, operator_max),
            ("recovery_samples", 2, 128),
            ("cache_max_bytes", 0, 1024 * 1024 * 1024),
            ("max_active_per_tenant", 1, operator_max),
            ("max_queued_per_tenant", 0, operator_queue_max),
        ):
            value = getattr(candidate, name)
            if type(value) is not int or not lower <= value <= upper:
                raise ValueError(f"{name} must be an integer in [{lower}, {upper}]")
        for name, lower, upper in (
            ("target_latency_ms", 100.0, 600_000.0),
            ("cooldown_seconds", 0.5, 300.0),
            ("max_queue_wait_seconds", 0.05, 3600.0),
            ("cache_ttl_seconds", 0.0, 86_400.0),
            ("memory_high_watermark", 0.5, 0.99),
            ("memory_low_watermark", 0.1, 0.95),
            ("background_starvation_seconds", 0.1, 3600.0),
            ("memory_shed_watermark", 0.5, 1.0),
        ):
            value = getattr(candidate, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not lower <= value <= upper
            ):
                raise ValueError(f"{name} must be finite in [{lower}, {upper}]")
        if candidate.min_effective_concurrency > candidate.max_effective_concurrency:
            raise ValueError("minimum serving concurrency exceeds maximum")
        if candidate.memory_low_watermark >= candidate.memory_high_watermark:
            raise ValueError("memory low watermark must be below high watermark")
        return candidate

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ServingResources:
    memory_used_fraction: float | None = None
    cpu_load_fraction: float | None = None
    process_rss_bytes: int | None = None
    available_memory_bytes: int | None = None
    source: str = "unavailable"

    def __post_init__(self) -> None:
        for name in ("memory_used_fraction", "cpu_load_fraction"):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
                or (name == "memory_used_fraction" and value > 1)
            ):
                raise ValueError(f"{name} must be a finite non-negative resource measurement")
        for name in ("process_rss_bytes", "available_memory_bytes"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"{name} must be a non-negative byte count")
        if not isinstance(self.source, str) or not self.source or len(self.source) > 256:
            raise ValueError("resource measurement source must be bounded")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class AdaptiveServingController:
    """Hysteretic feedback, not an activation identity or a model update."""

    def __init__(self, operator_max: int, operator_queue_max: int = 256) -> None:
        self.operator_max = operator_max
        self.operator_queue_max = operator_queue_max
        self.policy = AdaptiveServingPolicy.defaults(operator_max, operator_queue_max)
        self.effective_concurrency = operator_max
        self.resources = ServingResources()
        self.latency_ewma_ms: float | None = None
        self.queue_wait_ewma_ms: float | None = None
        self.failure_ewma = 0.0
        self.observations = 0
        self.samples = 0
        self.adjustments = 0
        self.level = "normal"
        self.reason = "within_operator_limits"
        self._healthy_samples = 0
        self._last_sample: float | None = None
        self._last_adjustment: float | None = None

    @staticmethod
    def _ewma(previous: float | None, value: float) -> float:
        return value if previous is None else previous + 0.2 * (value - previous)

    def configure(self, values: Mapping[str, Any], now: float) -> None:
        policy = self.policy.updated(values, self.operator_max, self.operator_queue_max)
        self.policy = policy
        ceiling = policy.max_effective_concurrency
        effective = min(ceiling, max(policy.min_effective_concurrency, self.effective_concurrency))
        if not policy.enabled:
            effective = ceiling
        if effective != self.effective_concurrency:
            self.effective_concurrency = effective
            self.adjustments += 1
            self._last_adjustment = now
        self._healthy_samples = 0
        self._last_sample = None

    def observe(self, *, elapsed_ms: float, queue_wait_ms: float, failed: bool) -> None:
        self.latency_ewma_ms = self._ewma(self.latency_ewma_ms, max(0.0, elapsed_ms))
        self.queue_wait_ewma_ms = self._ewma(self.queue_wait_ewma_ms, max(0.0, queue_wait_ms))
        self.failure_ewma = self._ewma(self.failure_ewma, 1.0 if failed else 0.0)
        self.observations += 1

    def sample_due(self, now: float) -> bool:
        return self._last_sample is None or now - self._last_sample >= 1.0

    def update(self, resources: ServingResources, *, now: float, queued: int) -> None:
        if not self.sample_due(now):
            return
        self.resources = resources
        self._last_sample = now
        self.samples += 1
        policy = self.policy
        memory = resources.memory_used_fraction
        cpu = resources.cpu_load_fraction
        critical = memory is not None and memory >= min(
            0.99, policy.memory_high_watermark + 0.05, policy.memory_shed_watermark,
        )
        reason = "within_operator_limits"
        if critical:
            reason = "memory_critical"
        elif memory is not None and memory >= policy.memory_high_watermark:
            reason = "memory_pressure"
        elif cpu is not None and cpu >= 0.95:
            reason = "cpu_pressure"
        elif self.observations >= 4 and self.failure_ewma >= 0.2:
            reason = "backend_failures"
        elif (
            self.observations >= 4
            and self.latency_ewma_ms is not None
            and self.latency_ewma_ms > policy.target_latency_ms * 1.25
        ):
            reason = "latency_pressure"
        pressured = reason != "within_operator_limits"
        healthy = (
            (memory is None or memory <= policy.memory_low_watermark)
            and (cpu is None or cpu < 0.85)
            and self.failure_ewma < 0.1
            and (self.latency_ewma_ms is None or self.latency_ewma_ms < policy.target_latency_ms * 0.85)
        )
        self.level = "critical" if critical else "elevated" if pressured else "normal" if healthy else "recovering"
        self.reason = reason if pressured else "within_operator_limits" if healthy else "hysteresis_recovery"
        self._healthy_samples = self._healthy_samples + 1 if healthy else 0
        if not policy.enabled:
            self.effective_concurrency = policy.max_effective_concurrency
            return
        can_adjust = self._last_adjustment is None or now - self._last_adjustment >= policy.cooldown_seconds
        if not can_adjust:
            return
        effective = self.effective_concurrency
        if pressured:
            effective = max(policy.min_effective_concurrency, effective // 2 if critical else effective - 1)
        elif queued and self._healthy_samples >= policy.recovery_samples:
            effective = min(policy.max_effective_concurrency, effective + 1)
        if effective != self.effective_concurrency:
            self.effective_concurrency = effective
            self.adjustments += 1
            self._last_adjustment = now
            self._healthy_samples = 0

    @property
    def background_limit(self) -> int:
        if self.policy.enabled and self.level == "critical":
            return 0
        # Leave one currently usable slot to interactive work when possible.
        return min(self.policy.background_max_concurrency, max(1, self.effective_concurrency - 1))

    def pressure_snapshot(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "reason": self.reason,
            "latency_ewma_ms": self.latency_ewma_ms,
            "queue_wait_ewma_ms": self.queue_wait_ewma_ms,
            "failure_ewma": self.failure_ewma,
            "observations": self.observations,
            "samples": self.samples,
            "adjustments": self.adjustments,
            "resource": self.resources.as_dict(),
        }
