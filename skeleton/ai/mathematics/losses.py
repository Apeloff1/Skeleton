"""Stable reference losses for training and evaluation parity checks."""
from __future__ import annotations

import math
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, finite_scalar, finite_vector, positive_scalar
from .numerics import compensated_sum, logsumexp
from .probability import normalize_distribution


def _paired(
    expected: Sequence[Real],
    predicted: Sequence[Real],
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    a = finite_vector("expected", expected)
    b = finite_vector("predicted", predicted)
    if len(a) != len(b):
        raise MathInvariantError(
            "loss vectors must have equal length",
            reason="dimension_mismatch",
            field="loss",
        )
    return a, b


def mean_squared_error(expected: Sequence[Real], predicted: Sequence[Real]) -> float:
    a, b = _paired(expected, predicted)
    return compensated_sum((x - y) ** 2 for x, y in zip(a, b)) / len(a)


def mean_absolute_error(expected: Sequence[Real], predicted: Sequence[Real]) -> float:
    a, b = _paired(expected, predicted)
    return compensated_sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def huber_loss(
    expected: Sequence[Real],
    predicted: Sequence[Real],
    *,
    delta: Real = 1.0,
) -> float:
    a, b = _paired(expected, predicted)
    threshold = positive_scalar("delta", delta)
    total = 0.0
    for expected_value, predicted_value in zip(a, b):
        error = abs(predicted_value - expected_value)
        total += (
            0.5 * error * error
            if error <= threshold
            else threshold * (error - 0.5 * threshold)
        )
    return total / len(a)


def binary_cross_entropy(
    targets: Sequence[Real],
    probabilities: Sequence[Real],
) -> float:
    y, p = _paired(targets, probabilities)
    total = 0.0
    for index, (target, probability) in enumerate(zip(y, p)):
        if not 0.0 <= target <= 1.0:
            raise MathInvariantError(
                "binary targets must lie in [0, 1]",
                reason="invalid_probability",
                field=f"targets[{index}]",
            )
        if not 0.0 <= probability <= 1.0:
            raise MathInvariantError(
                "binary probabilities must lie in [0, 1]",
                reason="invalid_probability",
                field=f"probabilities[{index}]",
            )
        if target > 0.0:
            if probability == 0.0:
                raise MathInvariantError(
                    "positive target has zero predicted support",
                    reason="zero_support_probability",
                    field=f"probabilities[{index}]",
                )
            total -= target * math.log(probability)
        if target < 1.0:
            if probability == 1.0:
                raise MathInvariantError(
                    "negative target has zero predicted support",
                    reason="zero_support_probability",
                    field=f"probabilities[{index}]",
                )
            total -= (1.0 - target) * math.log1p(-probability)
    return total / len(y)


def cross_entropy_from_logits(logits: Sequence[Real], target_index: int) -> float:
    values = finite_vector("logits", logits)
    if (
        isinstance(target_index, bool)
        or not isinstance(target_index, int)
        or not 0 <= target_index < len(values)
    ):
        raise MathInvariantError(
            "target_index is out of range",
            reason="invalid_target_index",
            field="target_index",
        )
    return logsumexp(values) - values[target_index]


def label_smoothed_cross_entropy_from_logits(
    logits: Sequence[Real],
    target_index: int,
    *,
    smoothing: Real = 0.1,
) -> float:
    values = finite_vector("logits", logits)
    if (
        isinstance(target_index, bool)
        or not isinstance(target_index, int)
        or not 0 <= target_index < len(values)
    ):
        raise MathInvariantError(
            "target_index is out of range",
            reason="invalid_target_index",
            field="target_index",
        )
    smooth = finite_scalar("smoothing", smoothing)
    if not 0.0 <= smooth < 1.0:
        raise MathInvariantError(
            "smoothing must lie in [0, 1)",
            reason="invalid_probability",
            field="smoothing",
        )
    normalizer = logsumexp(values)
    log_probabilities = tuple(value - normalizer for value in values)
    if len(values) == 1:
        return -log_probabilities[0]
    off_target = smooth / (len(values) - 1)
    return -compensated_sum(
        ((1.0 - smooth) if index == target_index else off_target) * log_probability
        for index, log_probability in enumerate(log_probabilities)
    )


def brier_score(probabilities: Sequence[Real], target_index: int) -> float:
    p = normalize_distribution(probabilities)
    if (
        isinstance(target_index, bool)
        or not isinstance(target_index, int)
        or not 0 <= target_index < len(p)
    ):
        raise MathInvariantError(
            "target_index is out of range",
            reason="invalid_target_index",
            field="target_index",
        )
    return compensated_sum(
        (probability - (1.0 if index == target_index else 0.0)) ** 2
        for index, probability in enumerate(p)
    )


def perplexity(mean_negative_log_likelihood: Real) -> float:
    value = finite_scalar("mean_negative_log_likelihood", mean_negative_log_likelihood)
    if value < 0.0:
        raise MathInvariantError(
            "mean negative log-likelihood must be non-negative",
            reason="negative_loss",
            field="mean_negative_log_likelihood",
        )
    if value > math.log(float.fromhex("0x1.fffffffffffffp+1023")):
        raise MathInvariantError(
            "perplexity would overflow finite float range",
            reason="non_finite_result",
            field="mean_negative_log_likelihood",
        )
    return math.exp(value)
