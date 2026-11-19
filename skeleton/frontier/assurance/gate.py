"""Bounded, explicitly boolean, fail-closed quality gate."""
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import islice

_MAX_CHECKS = 4096


@dataclass(frozen=True)
class QualityGate:
    checks: tuple[bool, ...]

    def __post_init__(self) -> None:
        if type(self.checks) is not tuple or len(self.checks) > _MAX_CHECKS:
            raise ValueError("invalid check inventory")
        if any(type(check) is not bool for check in self.checks):
            raise ValueError("checks must be explicit booleans")

    @classmethod
    def from_checks(cls, checks: Iterable[bool]) -> "QualityGate":
        return cls(tuple(islice(checks, _MAX_CHECKS + 1)))

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(self.checks)

    def require(self) -> None:
        if not self.passed:
            raise RuntimeError("quality gate failed")
