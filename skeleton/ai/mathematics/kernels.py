"""Positive-semidefinite kernel references and distribution comparison."""
from __future__ import annotations

import math
from numbers import Real
from typing import Callable, Sequence

from .contracts import MathInvariantError, Matrix, Vector, finite_scalar, finite_vector, positive_scalar
from .linear import dot
from .numerics import compensated_sum


Kernel = Callable[[Vector, Vector], float]


def _pair(left: Sequence[Real], right: Sequence[Real]) -> tuple[Vector, Vector]:
    a = finite_vector("left", left)
    b = finite_vector("right", right)
    if len(a) != len(b):
        raise MathInvariantError(
            "kernel vectors must have equal dimension",
            reason="dimension_mismatch",
            field="kernel",
        )
    return a, b


def linear_kernel(left: Sequence[Real], right: Sequence[Real]) -> float:
    a, b = _pair(left, right)
    return dot(a, b)


def polynomial_kernel(
    left: Sequence[Real],
    right: Sequence[Real],
    *,
    degree: int = 2,
    scale: Real = 1.0,
    offset: Real = 1.0,
) -> float:
    if isinstance(degree, bool) or not isinstance(degree, int) or degree < 1:
        raise MathInvariantError(
            "polynomial-kernel degree must be a positive integer",
            reason="invalid_kernel_degree",
            field="degree",
        )
    factor = positive_scalar("scale", scale)
    bias = finite_scalar("offset", offset)
    a, b = _pair(left, right)
    return finite_scalar("kernel_value", (factor * dot(a, b) + bias) ** degree)


def rbf_kernel(
    left: Sequence[Real],
    right: Sequence[Real],
    *,
    gamma: Real = 1.0,
) -> float:
    coefficient = positive_scalar("gamma", gamma)
    a, b = _pair(left, right)
    squared = compensated_sum((x - y) ** 2 for x, y in zip(a, b))
    return math.exp(-coefficient * squared)


def laplacian_kernel(
    left: Sequence[Real],
    right: Sequence[Real],
    *,
    gamma: Real = 1.0,
) -> float:
    coefficient = positive_scalar("gamma", gamma)
    a, b = _pair(left, right)
    distance = compensated_sum(abs(x - y) for x, y in zip(a, b))
    return math.exp(-coefficient * distance)


def gram_matrix(
    samples: Sequence[Sequence[Real]],
    kernel: Kernel,
) -> Matrix:
    if not samples:
        raise MathInvariantError(
            "kernel samples must not be empty",
            reason="empty_matrix",
            field="samples",
        )
    rows = tuple(finite_vector(f"samples[{index}]", row) for index, row in enumerate(samples))
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise MathInvariantError(
            "kernel samples must have consistent dimension",
            reason="ragged_matrix",
            field="samples",
        )
    output = []
    for i, left in enumerate(rows):
        result_row = []
        for j, right in enumerate(rows):
            value = finite_scalar(f"kernel[{i},{j}]", kernel(left, right))
            result_row.append(value)
        output.append(tuple(result_row))
    return tuple(output)


def centered_gram(matrix: Sequence[Sequence[Real]]) -> Matrix:
    rows = tuple(finite_vector(f"matrix[{index}]", row) for index, row in enumerate(matrix))
    n = len(rows)
    if not rows or len(rows[0]) != n or any(len(row) != n for row in rows):
        raise MathInvariantError(
            "Gram matrix must be square",
            reason="non_square_matrix",
            field="matrix",
        )
    row_means = tuple(compensated_sum(row) / n for row in rows)
    column_means = tuple(
        compensated_sum(rows[i][j] for i in range(n)) / n
        for j in range(n)
    )
    grand_mean = compensated_sum(row_means) / n
    return tuple(
        tuple(
            rows[i][j] - row_means[i] - column_means[j] + grand_mean
            for j in range(n)
        )
        for i in range(n)
    )


def maximum_mean_discrepancy_squared(
    left_samples: Sequence[Sequence[Real]],
    right_samples: Sequence[Sequence[Real]],
    kernel: Kernel,
    *,
    unbiased: bool = True,
) -> float:
    left = tuple(finite_vector(f"left_samples[{i}]", row) for i, row in enumerate(left_samples))
    right = tuple(finite_vector(f"right_samples[{i}]", row) for i, row in enumerate(right_samples))
    if not left or not right:
        raise MathInvariantError(
            "MMD requires non-empty sample sets",
            reason="empty_sample_set",
            field="samples",
        )
    width = len(left[0])
    if any(len(row) != width for row in left + right):
        raise MathInvariantError(
            "MMD sample dimensions must match",
            reason="dimension_mismatch",
            field="samples",
        )
    m = len(left)
    n = len(right)
    if unbiased and (m < 2 or n < 2):
        raise MathInvariantError(
            "unbiased MMD requires at least two samples per set",
            reason="insufficient_observations",
            field="samples",
        )

    if unbiased:
        xx = compensated_sum(
            finite_scalar("kernel_value", kernel(left[i], left[j]))
            for i in range(m)
            for j in range(m)
            if i != j
        ) / (m * (m - 1))
        yy = compensated_sum(
            finite_scalar("kernel_value", kernel(right[i], right[j]))
            for i in range(n)
            for j in range(n)
            if i != j
        ) / (n * (n - 1))
    else:
        xx = compensated_sum(
            finite_scalar("kernel_value", kernel(a, b))
            for a in left
            for b in left
        ) / (m * m)
        yy = compensated_sum(
            finite_scalar("kernel_value", kernel(a, b))
            for a in right
            for b in right
        ) / (n * n)

    xy = compensated_sum(
        finite_scalar("kernel_value", kernel(a, b))
        for a in left
        for b in right
    ) / (m * n)
    value = xx + yy - 2.0 * xy
    if value < 0.0 and abs(value) <= 1e-12:
        return 0.0
    return finite_scalar("mmd_squared", value)
