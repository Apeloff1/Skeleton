"""Structured matrix constructors and Gershgorin diagnostics."""
from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Matrix, Vector, finite_matrix, finite_vector
from .numerics import compensated_sum


def toeplitz(
    first_column: Sequence[Real],
    first_row: Sequence[Real],
) -> Matrix:
    column = finite_vector("first_column", first_column)
    row = finite_vector("first_row", first_row)
    if column[0] != row[0]:
        raise MathInvariantError(
            "Toeplitz first row and column must share the same origin value",
            reason="inconsistent_structure",
            field="origin",
        )
    return tuple(
        tuple(
            row[j - i] if j >= i else column[i - j]
            for j in range(len(row))
        )
        for i in range(len(column))
    )


def circulant(first_row: Sequence[Real]) -> Matrix:
    row = finite_vector("first_row", first_row)
    n = len(row)
    return tuple(
        tuple(row[(column - i) % n] for column in range(n))
        for i in range(n)
    )


@dataclass(frozen=True, slots=True)
class GershgorinDisc:
    center: float
    radius: float
    row: int


def gershgorin_discs(matrix: Sequence[Sequence[Real]]) -> tuple[GershgorinDisc, ...]:
    source = finite_matrix("matrix", matrix)
    n = len(source)
    if len(source[0]) != n:
        raise MathInvariantError(
            "Gershgorin analysis requires a square matrix",
            reason="non_square_matrix",
            field="matrix",
        )
    return tuple(
        GershgorinDisc(
            center=source[i][i],
            radius=compensated_sum(abs(source[i][j]) for j in range(n) if j != i),
            row=i,
        )
        for i in range(n)
    )


def diagonal_dominance_margins(matrix: Sequence[Sequence[Real]]) -> Vector:
    source = finite_matrix("matrix", matrix)
    n = len(source)
    if len(source[0]) != n:
        raise MathInvariantError(
            "diagonal dominance requires a square matrix",
            reason="non_square_matrix",
            field="matrix",
        )
    return tuple(
        abs(source[i][i])
        - compensated_sum(abs(source[i][j]) for j in range(n) if j != i)
        for i in range(n)
    )


def is_strictly_diagonally_dominant(matrix: Sequence[Sequence[Real]]) -> bool:
    return all(margin > 0.0 for margin in diagonal_dominance_margins(matrix))


def symmetrize(matrix: Sequence[Sequence[Real]]) -> Matrix:
    source = finite_matrix("matrix", matrix)
    n = len(source)
    if len(source[0]) != n:
        raise MathInvariantError(
            "symmetrization requires a square matrix",
            reason="non_square_matrix",
            field="matrix",
        )
    return tuple(
        tuple(0.5 * (source[i][j] + source[j][i]) for j in range(n))
        for i in range(n)
    )
