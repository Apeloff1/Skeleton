"""Family-wise and false-discovery-rate multiple-testing corrections."""
from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Vector, finite_scalar


@dataclass(frozen=True, slots=True)
class MultipleTestingReport:
    method: str
    raw_p_values: Vector
    adjusted_p_values: Vector
    rejected: tuple[bool, ...]
    alpha: float
    hypotheses: int


def _validate(p_values: Sequence[Real], alpha: Real) -> tuple[Vector, float]:
    if not p_values:
        raise MathInvariantError(
            "multiple testing requires at least one p-value",
            reason="empty_vector",
            field="p_values",
        )
    raw = []
    for index, value in enumerate(p_values):
        p = finite_scalar(f"p_values[{index}]", value)
        if not 0.0 <= p <= 1.0:
            raise MathInvariantError(
                "p-values must lie in [0, 1]",
                reason="invalid_probability",
                field=f"p_values[{index}]",
            )
        raw.append(p)
    level = finite_scalar("alpha", alpha)
    if not 0.0 < level < 1.0:
        raise MathInvariantError(
            "alpha must lie in (0, 1)",
            reason="invalid_probability",
            field="alpha",
        )
    return tuple(raw), level


def _report(method: str, raw: Vector, adjusted: Vector, alpha: float) -> MultipleTestingReport:
    return MultipleTestingReport(
        method=method,
        raw_p_values=raw,
        adjusted_p_values=adjusted,
        rejected=tuple(value <= alpha for value in adjusted),
        alpha=alpha,
        hypotheses=len(raw),
    )


def bonferroni(
    p_values: Sequence[Real],
    *,
    alpha: Real = 0.05,
) -> MultipleTestingReport:
    raw, level = _validate(p_values, alpha)
    adjusted = tuple(min(1.0, len(raw) * value) for value in raw)
    return _report("bonferroni", raw, adjusted, level)


def holm(
    p_values: Sequence[Real],
    *,
    alpha: Real = 0.05,
) -> MultipleTestingReport:
    raw, level = _validate(p_values, alpha)
    m = len(raw)
    order = sorted(range(m), key=lambda index: (raw[index], index))
    sorted_adjusted = [0.0] * m
    running = 0.0
    for position, index in enumerate(order):
        candidate = (m - position) * raw[index]
        running = max(running, candidate)
        sorted_adjusted[position] = min(1.0, running)
    adjusted = [0.0] * m
    for position, index in enumerate(order):
        adjusted[index] = sorted_adjusted[position]
    return _report("holm", raw, tuple(adjusted), level)


def benjamini_hochberg(
    p_values: Sequence[Real],
    *,
    alpha: Real = 0.05,
) -> MultipleTestingReport:
    raw, level = _validate(p_values, alpha)
    m = len(raw)
    order = sorted(range(m), key=lambda index: (raw[index], index))
    sorted_adjusted = [1.0] * m
    running = 1.0
    for position in range(m - 1, -1, -1):
        index = order[position]
        rank = position + 1
        running = min(running, m * raw[index] / rank)
        sorted_adjusted[position] = min(1.0, running)
    adjusted = [0.0] * m
    for position, index in enumerate(order):
        adjusted[index] = sorted_adjusted[position]
    return _report("benjamini_hochberg", raw, tuple(adjusted), level)


def benjamini_yekutieli(
    p_values: Sequence[Real],
    *,
    alpha: Real = 0.05,
) -> MultipleTestingReport:
    raw, level = _validate(p_values, alpha)
    m = len(raw)
    harmonic = sum(1.0 / rank for rank in range(1, m + 1))
    order = sorted(range(m), key=lambda index: (raw[index], index))
    sorted_adjusted = [1.0] * m
    running = 1.0
    for position in range(m - 1, -1, -1):
        index = order[position]
        rank = position + 1
        running = min(running, harmonic * m * raw[index] / rank)
        sorted_adjusted[position] = min(1.0, running)
    adjusted = [0.0] * m
    for position, index in enumerate(order):
        adjusted[index] = sorted_adjusted[position]
    return _report("benjamini_yekutieli", raw, tuple(adjusted), level)
