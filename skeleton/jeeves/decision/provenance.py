from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite


class ProvenanceKind(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    TERTIARY = "tertiary"
    BLOCKING = "blocking"
    ADVISORY = "advisory"


@dataclass(frozen=True, slots=True)
class ProvenanceRule:
    name: str
    kind: ProvenanceKind
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


_KIND_CYCLE = (
    ProvenanceKind.PRIMARY,
    ProvenanceKind.SECONDARY,
    ProvenanceKind.TERTIARY,
    ProvenanceKind.BLOCKING,
    ProvenanceKind.ADVISORY,
)

_RULE_COUNT = 180

RULES = tuple(
    ProvenanceRule(
        name=f"provenance_{index:03d}",
        kind=_KIND_CYCLE[index % len(_KIND_CYCLE)],
        threshold=(index % 100) / 100,
        rationale=f"bounded provenance rule {index}",
    )
    for index in range(1, _RULE_COUNT + 1)
)


def active(value: float):
    return tuple(rule.name for rule in RULES if rule.applies(value))


def by_kind(kind: ProvenanceKind):
    return tuple(rule for rule in RULES if rule.kind is kind)
