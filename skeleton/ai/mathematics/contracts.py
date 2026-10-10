"""Fail-closed mathematical contracts for the canonical AI tree.

This module owns representation and validation only.  It deliberately carries no
model-routing, knowledge, promotion, or execution authority.
"""
from __future__ import annotations

import math
from numbers import Real
from typing import Iterable, Sequence

Vector = tuple[float, ...]
Matrix = tuple[Vector, ...]


class MathInvariantError(ValueError):
    """Raised when mathematical input violates a deterministic invariant."""

    def __init__(self, message: str, *, reason: str, field: str | None = None) -> None:
        super().__init__(message)
        self.reason = reason
        self.field = field


def finite_scalar(name: str, value: Real) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise MathInvariantError(
            f"{name} must be a real scalar",
            reason="invalid_scalar_type",
            field=name,
        )
    out = float(value)
    if not math.isfinite(out):
        raise MathInvariantError(
            f"{name} must be finite",
            reason="non_finite_scalar",
            field=name,
        )
    return out


def finite_vector(
    name: str,
    values: Sequence[Real] | Iterable[Real],
    *,
    allow_empty: bool = False,
) -> Vector:
    if isinstance(values, (str, bytes)):
        raise MathInvariantError(
            f"{name} must be a numeric vector",
            reason="invalid_vector_type",
            field=name,
        )
    try:
        out = tuple(finite_scalar(f"{name}[{index}]", value) for index, value in enumerate(values))
    except TypeError as exc:
        raise MathInvariantError(
            f"{name} must be iterable",
            reason="invalid_vector_type",
            field=name,
        ) from exc
    if not out and not allow_empty:
        raise MathInvariantError(
            f"{name} must not be empty",
            reason="empty_vector",
            field=name,
        )
    return out


def finite_matrix(
    name: str,
    rows: Sequence[Sequence[Real]] | Iterable[Sequence[Real]],
    *,
    allow_empty: bool = False,
) -> Matrix:
    if isinstance(rows, (str, bytes)):
        raise MathInvariantError(
            f"{name} must be a matrix",
            reason="invalid_matrix_type",
            field=name,
        )
    try:
        matrix = tuple(
            finite_vector(f"{name}[{index}]", row, allow_empty=False)
            for index, row in enumerate(rows)
        )
    except TypeError as exc:
        raise MathInvariantError(
            f"{name} must be iterable",
            reason="invalid_matrix_type",
            field=name,
        ) from exc
    if not matrix:
        if allow_empty:
            return ()
        raise MathInvariantError(
            f"{name} must not be empty",
            reason="empty_matrix",
            field=name,
        )
    width = len(matrix[0])
    if any(len(row) != width for row in matrix):
        raise MathInvariantError(
            f"{name} must be rectangular",
            reason="ragged_matrix",
            field=name,
        )
    return matrix


def same_length(name: str, left: Sequence[object], right: Sequence[object]) -> None:
    if len(left) != len(right):
        raise MathInvariantError(
            f"{name} dimension mismatch: {len(left)} != {len(right)}",
            reason="dimension_mismatch",
            field=name,
        )


def positive_scalar(name: str, value: Real) -> float:
    out = finite_scalar(name, value)
    if out <= 0.0:
        raise MathInvariantError(
            f"{name} must be > 0",
            reason="non_positive_scalar",
            field=name,
        )
    return out


def non_negative_scalar(name: str, value: Real) -> float:
    out = finite_scalar(name, value)
    if out < 0.0:
        raise MathInvariantError(
            f"{name} must be >= 0",
            reason="negative_scalar",
            field=name,
        )
    return out
