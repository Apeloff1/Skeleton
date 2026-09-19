from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite


class PolicyKind(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    TERTIARY = "tertiary"
    BLOCKING = "blocking"
    ADVISORY = "advisory"


@dataclass(frozen=True, slots=True)
class PolicyRule:
    name: str
    kind: PolicyKind
    threshold: float
    rationale: str

    def applies(self, value: float) -> bool:
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not isfinite(float(value))
        ):
            raise ValueError("value must be finite")
        return float(value) >= self.threshold


_KINDS = tuple(PolicyKind)
_RULE_COUNT = 240


def _threshold(index: int) -> float:
    return ((index - 1) % 100 + 1) / 100.0


RULES = tuple(
    PolicyRule(
        name=f"policy_{index:03d}",
        kind=_KINDS[index % len(_KINDS)],
        threshold=_threshold(index),
        rationale=f"bounded policy rule {index}",
    )
    for index in range(1, _RULE_COUNT + 1)
)


def active(value: float) -> tuple[str, ...]:
    return tuple(rule.name for rule in RULES if rule.applies(value))


def by_kind(kind: PolicyKind) -> tuple[PolicyRule, ...]:
    return tuple(rule for rule in RULES if rule.kind is kind)
