"""Composable fail-closed quality gate."""
from dataclasses import dataclass
from typing import Iterable


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
