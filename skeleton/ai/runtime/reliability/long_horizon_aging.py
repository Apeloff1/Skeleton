"""Long-horizon aging, soak, expiry, and retirement controls.

Short-lived happy-path runs do not exercise TTL expiry, slow resource growth,
credential revalidation, certificate/model/provider retirement, or identifier
exhaustion. This module provides deterministic accelerated-time evaluation and
bounded soak-growth checks so aging changes are explicit and fail closed.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Mapping


class LongHorizonAgingError(ValueError):
    """Aging inputs or policy violate deterministic safety bounds."""


def _time(value: float, field: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0.0
    ):
        raise LongHorizonAgingError(f"{field} must be finite and non-negative")
    return float(value)


def _count(value: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise LongHorizonAgingError(f"{field} must be non-negative integer")
    return value


def _token(value: str, field: str, *, maximum: int = 192) -> str:
    if not isinstance(value, str):
        raise LongHorizonAgingError(f"{field} must be text")
    if (
        not value
        or value != value.strip()
        or len(value) > maximum
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise LongHorizonAgingError(f"invalid {field}")
    return value


@dataclass(frozen=True, slots=True)
class AgingPolicy:
    max_queue_depth: int = 100_000
    max_cache_entries: int = 1_000_000
    max_log_bytes: int = 10_000_000_000
    max_identifier: int = 2**63 - 1

    def __post_init__(self) -> None:
        for name in (
            "max_queue_depth",
            "max_cache_entries",
            "max_log_bytes",
            "max_identifier",
        ):
            if _count(getattr(self, name), name) < 1:
                raise LongHorizonAgingError(f"{name} must be positive")


@dataclass(frozen=True, slots=True)
class LifecycleResource:
    name: str
    kind: str
    activated_at: float
    expires_at: float | None = None
    retires_at: float | None = None
    replacement: str | None = None
    revalidate_every_seconds: float | None = None

    def __post_init__(self) -> None:
        _token(self.name, "resource name")
        _token(self.kind, "resource kind", maximum=96)
        activated = _time(self.activated_at, "activated_at")
        if self.expires_at is not None:
            expires = _time(self.expires_at, "expires_at")
            if expires <= activated:
                raise LongHorizonAgingError("expires_at must follow activation")
        if self.retires_at is not None:
            retires = _time(self.retires_at, "retires_at")
            if retires <= activated:
                raise LongHorizonAgingError("retires_at must follow activation")
            if self.replacement is not None:
                _token(self.replacement, "replacement")
        elif self.replacement is not None:
            raise LongHorizonAgingError(
                "replacement requires an explicit retirement time"
            )
        if self.revalidate_every_seconds is not None:
            if _time(
                self.revalidate_every_seconds,
                "revalidate_every_seconds",
            ) <= 0:
                raise LongHorizonAgingError(
                    "revalidate_every_seconds must be positive"
                )


@dataclass(frozen=True, slots=True)
class GrowthBudget:
    metric: str
    max_value: int
    max_growth_per_hour: float

    def __post_init__(self) -> None:
        _token(self.metric, "metric", maximum=96)
        if _count(self.max_value, "max_value") < 1:
            raise LongHorizonAgingError("max_value must be positive")
        growth = _time(self.max_growth_per_hour, "max_growth_per_hour")
        if growth < 0:
            raise LongHorizonAgingError(
                "max_growth_per_hour must be non-negative"
            )


@dataclass(frozen=True, slots=True)
class SoakReport:
    sample_count: int
    duration_seconds: float
    violations: tuple[str, ...]

    @property
    def safe(self) -> bool:
        return not self.violations


@dataclass(frozen=True, slots=True)
class AgingReport:
    evaluated_at: float
    expired: tuple[str, ...]
    retirement_due: tuple[str, ...]
    migration_blocked: tuple[str, ...]
    revalidation_due: tuple[str, ...]
    bounds_exceeded: tuple[str, ...]

    @property
    def safe(self) -> bool:
        return not (
            self.expired
            or self.migration_blocked
            or self.revalidation_due
            or self.bounds_exceeded
        )


class SoakWindow:
    """Deterministic long-run metric window with absolute and growth bounds."""

    def __init__(self) -> None:
        self._samples: list[tuple[float, dict[str, int]]] = []

    def add_sample(
        self,
        *,
        at: float,
        metrics: Mapping[str, int],
    ) -> None:
        at = _time(at, "sample time")
        if self._samples and at <= self._samples[-1][0]:
            raise LongHorizonAgingError(
                "soak sample times must be strictly increasing"
            )
        if not isinstance(metrics, Mapping) or not metrics:
            raise LongHorizonAgingError("soak metrics must be non-empty mapping")
        normalized: dict[str, int] = {}
        for metric, value in metrics.items():
            normalized[_token(metric, "metric", maximum=96)] = _count(
                value,
                f"metric {metric}",
            )
        self._samples.append((at, normalized))

    def evaluate(self, budgets: Iterable[GrowthBudget]) -> SoakReport:
        budget_rows = tuple(budgets)
        if not budget_rows:
            raise LongHorizonAgingError("soak evaluation requires budgets")
        if len({row.metric for row in budget_rows}) != len(budget_rows):
            raise LongHorizonAgingError("duplicate soak metric budget")
        if len(self._samples) < 2:
            raise LongHorizonAgingError(
                "soak evaluation requires at least two samples"
            )

        first_at, first = self._samples[0]
        last_at, last = self._samples[-1]
        duration = last_at - first_at
        if duration <= 0:
            raise LongHorizonAgingError("soak duration must be positive")

        violations: list[str] = []
        for budget in sorted(budget_rows, key=lambda row: row.metric):
            values = [
                metrics[budget.metric]
                for _at, metrics in self._samples
                if budget.metric in metrics
            ]
            if len(values) != len(self._samples):
                violations.append(f"{budget.metric}:missing_sample")
                continue
            maximum = max(values)
            if maximum > budget.max_value:
                violations.append(
                    f"{budget.metric}:max_value:{maximum}>{budget.max_value}"
                )
            growth = max(0, last[budget.metric] - first[budget.metric])
            growth_per_hour = growth * 3600.0 / duration
            if growth_per_hour > budget.max_growth_per_hour:
                violations.append(
                    f"{budget.metric}:growth_per_hour:"
                    f"{growth_per_hour:.6f}>{budget.max_growth_per_hour:.6f}"
                )

        return SoakReport(
            sample_count=len(self._samples),
            duration_seconds=duration,
            violations=tuple(violations),
        )


class LongHorizonAgingGuard:
    """Evaluate future lifecycle state and bounded resource growth."""

    def __init__(self, policy: AgingPolicy | None = None) -> None:
        self.policy = policy or AgingPolicy()
        if not isinstance(self.policy, AgingPolicy):
            raise TypeError("policy must be AgingPolicy")

    @staticmethod
    def accelerated_times(
        *,
        start: float,
        horizon_seconds: float,
        step_seconds: float,
    ) -> tuple[float, ...]:
        start = _time(start, "start")
        horizon = _time(horizon_seconds, "horizon_seconds")
        step = _time(step_seconds, "step_seconds")
        if horizon <= 0 or step <= 0:
            raise LongHorizonAgingError(
                "accelerated-time horizon and step must be positive"
            )
        end = start + horizon
        values = [start]
        current = start
        while current + step < end:
            current += step
            values.append(current)
        if values[-1] != end:
            values.append(end)
        return tuple(values)

    def evaluate(
        self,
        resources: Iterable[LifecycleResource],
        *,
        now: float,
        queue_depth: int,
        cache_entries: int,
        log_bytes: int,
        next_identifier: int,
        ready_replacements: Iterable[str] = (),
        last_revalidated_at: Mapping[str, float] | None = None,
    ) -> AgingReport:
        now = _time(now, "now")
        rows = tuple(resources)
        if len({row.name for row in rows}) != len(rows):
            raise LongHorizonAgingError("lifecycle resource names must be unique")
        if any(not isinstance(row, LifecycleResource) for row in rows):
            raise TypeError("resources must contain LifecycleResource")

        ready = frozenset(
            _token(item, "ready replacement")
            for item in ready_replacements
        )
        revalidated = dict(last_revalidated_at or {})

        expired: list[str] = []
        retirement_due: list[str] = []
        migration_blocked: list[str] = []
        revalidation_due: list[str] = []

        for row in sorted(rows, key=lambda item: item.name):
            if now < row.activated_at:
                continue
            if row.expires_at is not None and now >= row.expires_at:
                expired.append(row.name)
            if row.retires_at is not None and now >= row.retires_at:
                retirement_due.append(row.name)
                if row.replacement is None or row.replacement not in ready:
                    migration_blocked.append(row.name)
            if row.revalidate_every_seconds is not None:
                last = revalidated.get(row.name, row.activated_at)
                last = _time(last, f"last_revalidated_at[{row.name}]")
                if last < row.activated_at or last > now:
                    raise LongHorizonAgingError(
                        f"invalid revalidation time for {row.name}"
                    )
                if now - last >= row.revalidate_every_seconds:
                    revalidation_due.append(row.name)

        values = {
            "queue_depth": _count(queue_depth, "queue_depth"),
            "cache_entries": _count(cache_entries, "cache_entries"),
            "log_bytes": _count(log_bytes, "log_bytes"),
            "next_identifier": _count(next_identifier, "next_identifier"),
        }
        limits = {
            "queue_depth": self.policy.max_queue_depth,
            "cache_entries": self.policy.max_cache_entries,
            "log_bytes": self.policy.max_log_bytes,
            "next_identifier": self.policy.max_identifier,
        }
        exceeded = tuple(
            f"{name}:{values[name]}>{limits[name]}"
            for name in sorted(values)
            if values[name] > limits[name]
        )

        return AgingReport(
            evaluated_at=now,
            expired=tuple(expired),
            retirement_due=tuple(retirement_due),
            migration_blocked=tuple(migration_blocked),
            revalidation_due=tuple(revalidation_due),
            bounds_exceeded=exceeded,
        )

    @staticmethod
    def require_safe(report: AgingReport) -> None:
        if not isinstance(report, AgingReport):
            raise TypeError("report must be AgingReport")
        if not report.safe:
            raise LongHorizonAgingError(
                "long-horizon aging safety violation: "
                f"expired={report.expired!r}; "
                f"migration_blocked={report.migration_blocked!r}; "
                f"revalidation_due={report.revalidation_due!r}; "
                f"bounds_exceeded={report.bounds_exceeded!r}"
            )


__all__ = [
    "AgingPolicy",
    "AgingReport",
    "GrowthBudget",
    "LifecycleResource",
    "LongHorizonAgingError",
    "LongHorizonAgingGuard",
    "SoakReport",
    "SoakWindow",
]
