"""Composable fail-closed quality gate."""

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class QualityGate:
    checks: tuple[bool, ...]

    @classmethod
    def from_checks(cls, checks: Iterable[bool]) -> "QualityGate":
        return cls(tuple(checks))

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(self.checks)

    def require(self) -> None:
        if not self.passed:
            raise RuntimeError("quality gate failed")
