"""Evidence-based game capability gaps for independent adversarial review.

Ranks measured coverage deficits; it does not invent model grades or empirical
predictions. Review receipts from the canonical adversarial worker are required
before a score may inform user-facing claims or training promotion.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite

from .dragon_microknowledge import FACTORS, _id


@dataclass(frozen=True, slots=True)
class CapabilityGap:
    factor: str
    value: str
    expected_checks: int
    passed_checks: int
    importance: float
    review_ref: str
    expires_at: float

    def __post_init__(self) -> None:
        if self.factor not in FACTORS:
            raise ValueError("unsupported gap dimension")
        _id(self.value); _id(self.review_ref)
        for v in (self.expected_checks, self.passed_checks):
            if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 10000:
                raise ValueError("invalid capability coverage")
        if not self.expected_checks or self.passed_checks > self.expected_checks:
            raise ValueError("invalid capability denominator")
        if isinstance(self.importance, bool) or not isfinite(self.importance) or not 0 <= self.importance <= 1:
            raise ValueError("invalid gap importance")
        if isinstance(self.expires_at, bool) or not isfinite(self.expires_at):
            raise ValueError("invalid review expiry")


@dataclass(frozen=True, slots=True)
class GapPriority:
    factor: str
    value: str
    score: float
    missing_checks: int
    query: str
    review_ref: str


def prioritize_gaps(gaps: tuple[CapabilityGap, ...], *, now: float,
                    max_results: int = 8) -> tuple[GapPriority, ...]:
    if len(gaps) > 128 or isinstance(max_results, bool) or not isinstance(max_results, int) or not 1 <= max_results <= 32:
        raise ValueError("gap matrix budget exceeded")
    if isinstance(now, bool) or not isfinite(now):
        raise ValueError("invalid review time")
    if len({(g.factor, g.value) for g in gaps}) != len(gaps):
        raise ValueError("duplicate capability gap")
    result = []
    for gap in gaps:
        if gap.expires_at <= now or gap.passed_checks == gap.expected_checks:
            continue
        missing = gap.expected_checks - gap.passed_checks
        result.append(GapPriority(gap.factor, gap.value,
            round(gap.importance * missing / gap.expected_checks, 6), missing,
            f"{gap.factor} {gap.value} game development primary technical documentation",
            gap.review_ref))
    return tuple(sorted(result, key=lambda g: (-g.score, g.factor, g.value))[:max_results])
