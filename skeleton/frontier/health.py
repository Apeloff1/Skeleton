"""Small health model for runtime and infrastructure gates."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum


class HealthState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class HealthReport:
    state: HealthState
    checks: Mapping[str, bool]

    @property
    def healthy(self) -> bool:
        return self.state is HealthState.HEALTHY


def evaluate_health(checks: Mapping[str, bool]) -> HealthReport:
    normalized = dict(checks)
    if not normalized or not any(normalized.values()):
        return HealthReport(HealthState.UNAVAILABLE, normalized)
    if all(normalized.values()):
        return HealthReport(HealthState.HEALTHY, normalized)
    return HealthReport(HealthState.DEGRADED, normalized)
