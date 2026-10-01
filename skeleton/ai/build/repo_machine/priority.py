"""Deterministic blocker-first repository priority decisions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


class PriorityPolicyError(RuntimeError):
    pass


def _id(value: str, field: str) -> str:
    text = str(value).strip()
    if not text or len(text) > 192:
        raise ValueError(f"{field} must be non-empty bounded text")
    return text


@dataclass(frozen=True, slots=True)
class HardBlocker:
    blocker_id: str
    rank: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "blocker_id", _id(self.blocker_id, "blocker_id"))
        if not isinstance(self.rank, int) or isinstance(self.rank, bool) or self.rank < 500:
            raise ValueError("hard blocker rank must be integer >= 500")


@dataclass(frozen=True, slots=True)
class PriorityDecision:
    stable_id: str
    hard_blocker_rank: int
    soft_score: int
    wait_cycles: int
    forced_review: bool
    sort_key: tuple[int, int, int, int, str]


def decide_priority(
    stable_id: str,
    *,
    blockers: tuple[HardBlocker, ...] = (),
    soft_factors: Mapping[str, int] | None = None,
    wait_cycles: int = 0,
    age_sequence: int = 0,
    max_soft_wait_cycles: int = 20,
    factor_bounds: Mapping[str, tuple[int, int]] | None = None,
    max_soft_factors: int = 16,
) -> PriorityDecision:
    stable = _id(stable_id, "stable_id")
    for name, value in (
        ("wait_cycles", wait_cycles),
        ("age_sequence", age_sequence),
        ("max_soft_wait_cycles", max_soft_wait_cycles),
        ("max_soft_factors", max_soft_factors),
    ):
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError(f"{name} must be an integer")
    if wait_cycles < 0 or age_sequence < 0 or max_soft_wait_cycles <= 0:
        raise ValueError("priority counters must be non-negative and wait bound positive")
    if max_soft_factors <= 0 or max_soft_factors > 64:
        raise ValueError("max_soft_factors must be in 1..64")
    blocker_ids = [item.blocker_id for item in blockers]
    if len(blocker_ids) != len(set(blocker_ids)):
        raise PriorityPolicyError("duplicate hard blocker identity")
    factors = dict(soft_factors or {})
    if len(factors) > max_soft_factors:
        raise PriorityPolicyError("too many soft priority factors")
    bounds = dict(factor_bounds or {})
    score = 0
    for name in sorted(factors):
        lname = name.lower()
        if "percent" in lname or "completion" in lname:
            raise PriorityPolicyError("completion percentage is not a priority input")
        value = factors[name]
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError(f"soft factor {name} must be integer")
        lower, upper = bounds.get(name, (-100, 100))
        if (
            not isinstance(lower, int)
            or isinstance(lower, bool)
            or not isinstance(upper, int)
            or isinstance(upper, bool)
        ):
            raise TypeError(f"factor bounds for {name} must be integers")
        if lower > upper or max(abs(lower), abs(upper)) > 100:
            raise PriorityPolicyError(f"invalid factor bounds for {name}")
        if not lower <= value <= upper:
            raise PriorityPolicyError(f"soft factor {name} is outside declared bounds")
        score += value

    hard_rank = max((item.rank for item in blockers), default=0)
    forced = not blockers and wait_cycles >= max_soft_wait_cycles
    # Hard blockers always outrank soft work. Forced review outranks ordinary
    # soft ordering but never outranks a hard blocker.
    sort_key = (
        -hard_rank,
        -int(forced),
        -score,
        age_sequence,
        stable,
    )
    return PriorityDecision(
        stable_id=stable,
        hard_blocker_rank=hard_rank,
        soft_score=score,
        wait_cycles=wait_cycles,
        forced_review=forced,
        sort_key=sort_key,
    )


__all__ = [
    "HardBlocker",
    "PriorityDecision",
    "PriorityPolicyError",
    "decide_priority",
]
