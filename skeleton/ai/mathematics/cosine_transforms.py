"""Orthonormal DCT-II/DCT-IV and separable 2-D cosine transforms."""
from __future__ import annotations

import math
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Matrix, Vector, finite_matrix, finite_vector


def dct_ii(values: Sequence[Real]) -> Vector:
    source = finite_vector("values", values)
    n = len(source)
    scale = math.sqrt(2.0 / n)
    output = []
    for k in range(n):
        alpha = 1.0 / math.sqrt(2.0) if k == 0 else 1.0
        total = sum(
            source[index] * math.cos(math.pi / n * (index + 0.5) * k)
            for index in range(n)
        )
        output.append(scale * alpha * total)
    return tuple(output)


def inverse_dct_ii(coefficients: Sequence[Real]) -> Vector:
    source = finite_vector("coefficients", coefficients)
    n = len(source)
    scale = math.sqrt(2.0 / n)
    output = []
    for index in range(n):
        total = 0.0
        for k, coefficient in enumerate(source):
            alpha = 1.0 / math.sqrt(2.0) if k == 0 else 1.0
            total += alpha * coefficient * math.cos(math.pi / n * (index + 0.5) * k)
        output.append(scale * total)
    return tuple(output)


def dct_iv(values: Sequence[Real]) -> Vector:
    source = finite_vector("values", values)
    n = len(source)
    scale = math.sqrt(2.0 / n)
    return tuple(
        scale * sum(
            source[index]
            * math.cos(math.pi / n * (index + 0.5) * (k + 0.5))
            for index in range(n)
        )
        for k in range(n)
    )


def _transpose_rectangular(matrix: Matrix) -> Matrix:
    return tuple(
        tuple(matrix[row][column] for row in range(len(matrix)))
        for column in range(len(matrix[0]))
    )


def dct2(matrix: Sequence[Sequence[Real]]) -> Matrix:
    source = finite_matrix("matrix", matrix)
    rows = tuple(dct_ii(row) for row in source)
    columns = _transpose_rectangular(rows)
    transformed_columns = tuple(dct_ii(column) for column in columns)
    return _transpose_rectangular(transformed_columns)


def inverse_dct2(matrix: Sequence[Sequence[Real]]) -> Matrix:
    source = finite_matrix("matrix", matrix)
    rows = tuple(inverse_dct_ii(row) for row in source)
    columns = _transpose_rectangular(rows)
    restored_columns = tuple(inverse_dct_ii(column) for column in columns)
    return _transpose_rectangular(restored_columns)
