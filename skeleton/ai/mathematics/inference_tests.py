"""Classical statistical-inference reference diagnostics."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .continuous_distributions import regularized_beta
from .contracts import MathInvariantError, Vector, finite_vector
from .distributions import normal_cdf
from .numerics import compensated_sum
from .rank_statistics import rankdata


def _mean_variance(values: Sequence[Real], name: str) -> tuple[Vector, float, float]:
    observations = finite_vector(name, values)
    if len(observations) < 2:
        raise MathInvariantError(
            "sample inference requires at least two observations",
            reason="insufficient_observations",
            field=name,
        )
    mean = compensated_sum(observations) / len(observations)
    variance = compensated_sum((value - mean) ** 2 for value in observations) / (len(observations) - 1)
    return observations, mean, variance


@dataclass(frozen=True, slots=True)
class WelchTReport:
    statistic: float
    degrees_of_freedom: float
    two_sided_p_value: float
    mean_difference: float
    standard_error: float


def welch_t_test(
    left: Sequence[Real],
    right: Sequence[Real],
) -> WelchTReport:
    a, mean_a, variance_a = _mean_variance(left, "left")
    b, mean_b, variance_b = _mean_variance(right, "right")
    contribution_a = variance_a / len(a)
    contribution_b = variance_b / len(b)
    variance_sum = contribution_a + contribution_b
    if variance_sum == 0.0:
        if mean_a == mean_b:
            return WelchTReport(0.0, math.inf, 1.0, 0.0, 0.0)
        raise MathInvariantError(
            "Welch t statistic is undefined for separated zero-variance samples",
            reason="zero_variance",
            field="samples",
        )
    standard_error = math.sqrt(variance_sum)
    statistic = (mean_a - mean_b) / standard_error
    denominator = (
        contribution_a * contribution_a / (len(a) - 1)
        + contribution_b * contribution_b / (len(b) - 1)
    )
    degrees = variance_sum * variance_sum / denominator
    x = degrees / (degrees + statistic * statistic)
    two_sided = regularized_beta(x, 0.5 * degrees, 0.5)
    return WelchTReport(
        statistic=statistic,
        degrees_of_freedom=degrees,
        two_sided_p_value=max(0.0, min(1.0, two_sided)),
        mean_difference=mean_a - mean_b,
        standard_error=standard_error,
    )


@dataclass(frozen=True, slots=True)
class MannWhitneyReport:
    u_left: float
    u_right: float
    z_score: float
    two_sided_p_value: float
    tie_correction: float


def mann_whitney_u(
    left: Sequence[Real],
    right: Sequence[Real],
) -> MannWhitneyReport:
    a = finite_vector("left", left)
    b = finite_vector("right", right)
    combined = a + b
    ranks = rankdata(combined)
    n1 = len(a)
    n2 = len(b)
    rank_sum_left = compensated_sum(ranks[:n1])
    u_left = rank_sum_left - n1 * (n1 + 1) / 2.0
    u_right = n1 * n2 - u_left

    counts: dict[float, int] = {}
    for value in combined:
        counts[value] = counts.get(value, 0) + 1
    total = n1 + n2
    tie_term = sum(count**3 - count for count in counts.values())
    tie_correction = 1.0 - tie_term / (total**3 - total) if total > 1 else 1.0
    variance = n1 * n2 * (total + 1) * tie_correction / 12.0
    if variance <= 0.0:
        raise MathInvariantError(
            "Mann-Whitney variance vanished under ties",
            reason="zero_variance",
            field="samples",
        )
    mean_u = n1 * n2 / 2.0
    z = (u_left - mean_u) / math.sqrt(variance)
    p = 2.0 * (1.0 - normal_cdf(abs(z)))
    return MannWhitneyReport(
        u_left=u_left,
        u_right=u_right,
        z_score=z,
        two_sided_p_value=max(0.0, min(1.0, p)),
        tie_correction=tie_correction,
    )


@dataclass(frozen=True, slots=True)
class ANOVAReport:
    f_statistic: float
    degrees_between: int
    degrees_within: int
    p_value: float
    between_sum_squares: float
    within_sum_squares: float


def one_way_anova(groups: Sequence[Sequence[Real]]) -> ANOVAReport:
    if len(groups) < 2:
        raise MathInvariantError(
            "ANOVA requires at least two groups",
            reason="insufficient_groups",
            field="groups",
        )
    clean = tuple(finite_vector(f"groups[{index}]", group) for index, group in enumerate(groups))
    if any(len(group) < 1 for group in clean):
        raise MathInvariantError(
            "ANOVA groups must be non-empty",
            reason="empty_vector",
            field="groups",
        )
    total_count = sum(len(group) for group in clean)
    if total_count <= len(clean):
        raise MathInvariantError(
            "ANOVA requires positive within-group degrees of freedom",
            reason="insufficient_observations",
            field="groups",
        )
    means = tuple(compensated_sum(group) / len(group) for group in clean)
    grand_mean = compensated_sum(
        value for group in clean for value in group
    ) / total_count
    between = compensated_sum(
        len(group) * (mean - grand_mean) ** 2
        for group, mean in zip(clean, means)
    )
    within = compensated_sum(
        (value - mean) ** 2
        for group, mean in zip(clean, means)
        for value in group
    )
    df_between = len(clean) - 1
    df_within = total_count - len(clean)
    if within == 0.0:
        if between == 0.0:
            return ANOVAReport(0.0, df_between, df_within, 1.0, 0.0, 0.0)
        return ANOVAReport(math.inf, df_between, df_within, 0.0, between, 0.0)
    f_statistic = (between / df_between) / (within / df_within)
    x = (df_between * f_statistic) / (df_between * f_statistic + df_within)
    cdf = regularized_beta(x, 0.5 * df_between, 0.5 * df_within)
    return ANOVAReport(
        f_statistic=f_statistic,
        degrees_between=df_between,
        degrees_within=df_within,
        p_value=max(0.0, min(1.0, 1.0 - cdf)),
        between_sum_squares=between,
        within_sum_squares=within,
    )
