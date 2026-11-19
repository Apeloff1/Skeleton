"""Fail-closed immutable health reports for Frontier runtime admission."""
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType


class HealthState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


def _state(checks: Mapping[str, bool]) -> HealthState:
    if not checks or not any(checks.values()):
        return HealthState.UNAVAILABLE
    if all(checks.values()):
        return HealthState.HEALTHY
    return HealthState.DEGRADED


def _validated(checks: Mapping[str, bool]) -> dict[str, bool]:
    if type(checks) not in (dict, MappingProxyType) or len(checks) > 4096:
        raise ValueError("invalid health inventory")
    result = dict(checks)
    if any(type(name) is not str or not name.strip() or len(name) > 256
           or type(value) is not bool for name, value in result.items()):
        raise ValueError("health inventory requires named boolean checks")
    return result


@dataclass(frozen=True, slots=True)
class HealthReport:
    state: HealthState
    checks: Mapping[str, bool]

    def __post_init__(self) -> None:
        validated = _validated(self.checks)
        if self.state is not _state(validated):
            raise ValueError("health state contradicts evidence")
        object.__setattr__(self, "checks", MappingProxyType(validated))

    @property
    def healthy(self) -> bool:
        return self.state is HealthState.HEALTHY


def evaluate_health(checks: Mapping[str, bool]) -> HealthReport:
    validated = _validated(checks)
    return HealthReport(_state(validated), validated)
