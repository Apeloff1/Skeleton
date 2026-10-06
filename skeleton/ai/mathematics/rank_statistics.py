"""Tie-aware rank and concordance statistics reference primitives."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Vector, finite_vector
from .statistics import correlation


def rankdata(values: Sequence[Real]) -> Vector:
    observations = finite_vector("values", values)
    order = sorted(range(len(observations)), key=lambda index: (observations[index], index))
    ranks = [0.0] * len(observations)
    cursor = 0
    while cursor < len(order):
        end = cursor + 1
        value = observations[order[cursor]]
        while end < len(order) and observations[order[end]] == value:
            end += 1
        # Ranks are one-based; tied observations receive their average rank.
        average = 0.5 * ((cursor + 1) + end)
        for position in range(cursor, end):
            ranks[order[position]] = average
        cursor = end
    return tuple(ranks)


def spearman_correlation(
    left: Sequence[Real],
    right: Sequence[Real],
) -> float:
    a = finite_vector("left", left)
    b = finite_vector("right", right)
    if len(a) != len(b):
        raise MathInvariantError(
            "Spearman inputs must have equal length",
            reason="dimension_mismatch",
            field="rank_correlation",
        )
    if len(a) < 2:
        raise MathInvariantError(
            "Spearman correlation requires at least two observations",
            reason="insufficient_observations",
            field="rank_correlation",
        )
    return correlation(rankdata(a), rankdata(b))


@dataclass(frozen=True, slots=True)
class KendallTauReport:
    tau_b: float
    concordant_pairs: int
    discordant_pairs: int
    ties_left_only: int
    ties_right_only: int
    ties_both: int
    comparable_pairs: int


def kendall_tau_b(
    left: Sequence[Real],
    right: Sequence[Real],
) -> KendallTauReport:
    a = finite_vector("left", left)
    b = finite_vector("right", right)
    if len(a) != len(b):
        raise MathInvariantError(
            "Kendall inputs must have equal length",
            reason="dimension_mismatch",
            field="rank_correlation",
        )
    if len(a) < 2:
        raise MathInvariantError(
            "Kendall tau requires at least two observations",
            reason="insufficient_observations",
            field="rank_correlation",
        )
    concordant = 0
    discordant = 0
    ties_left = 0
    ties_right = 0
    ties_both = 0
    for i in range(len(a)):
        for j in range(i + 1, len(a)):
            dx = a[j] - a[i]
            dy = b[j] - b[i]
            if dx == 0.0 and dy == 0.0:
                ties_both += 1
            elif dx == 0.0:
                ties_left += 1
            elif dy == 0.0:
                ties_right += 1
            elif dx * dy > 0.0:
                concordant += 1
            else:
                discordant += 1

    numerator = concordant - discordant
    left_denom = concordant + discordant + ties_left
    right_denom = concordant + discordant + ties_right
    denominator = math.sqrt(left_denom * right_denom)
    if denominator == 0.0:
        raise MathInvariantError(
            "Kendall tau-b is undefined when one ranking has no comparable variation",
            reason="zero_variance",
            field="rank_correlation",
        )
    return KendallTauReport(
        tau_b=numerator / denominator,
        concordant_pairs=concordant,
        discordant_pairs=discordant,
        ties_left_only=ties_left,
        ties_right_only=ties_right,
        ties_both=ties_both,
        comparable_pairs=concordant + discordant,
    )


def rank_biserial_correlation(
    values: Sequence[Real],
    groups: Sequence[bool | int],
) -> float:
    observations = finite_vector("values", values)
    if len(observations) != len(groups):
        raise MathInvariantError(
            "rank-biserial inputs must have equal length",
            reason="dimension_mismatch",
            field="groups",
        )
    clean_groups: list[int] = []
    for index, group in enumerate(groups):
        if isinstance(group, bool):
            clean_groups.append(int(group))
        elif isinstance(group, int) and group in {0, 1}:
            clean_groups.append(group)
        else:
            raise MathInvariantError(
                "rank-biserial groups must be booleans or 0/1 integers",
                reason="invalid_group",
                field=f"groups[{index}]",
            )
    n0 = clean_groups.count(0)
    n1 = clean_groups.count(1)
    if n0 == 0 or n1 == 0:
        raise MathInvariantError(
            "rank-biserial correlation requires both groups",
            reason="insufficient_groups",
            field="groups",
        )
    ranks = rankdata(observations)
    rank_sum_one = sum(rank for rank, group in zip(ranks, clean_groups) if group == 1)
    u_one = rank_sum_one - n1 * (n1 + 1) / 2.0
    return 2.0 * u_one / (n0 * n1) - 1.0
