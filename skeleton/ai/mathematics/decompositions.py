"""Dense matrix decompositions and least-squares reference routines."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Matrix, Vector, finite_matrix, finite_vector, positive_scalar
from .linear import dot, l2_norm, matvec, transpose
from .numerics import compensated_sum


@dataclass(frozen=True, slots=True)
class CholeskyReport:
    lower: Matrix
    reconstruction_linf: float
    minimum_diagonal: float
    maximum_diagonal: float
    diagonal_condition_proxy: float


def cholesky_decompose(
    matrix: Sequence[Sequence[Real]],
    *,
    symmetry_tolerance: Real = 1e-12,
    positive_tolerance: Real = 1e-14,
) -> CholeskyReport:
    source = finite_matrix("matrix", matrix)
    n = len(source)
    if len(source[0]) != n:
        raise MathInvariantError(
            "Cholesky decomposition requires a square matrix",
            reason="non_square_matrix",
            field="matrix",
        )
    sym_tol = positive_scalar("symmetry_tolerance", symmetry_tolerance)
    pos_tol = positive_scalar("positive_tolerance", positive_tolerance)
    scale = max(1.0, max(abs(value) for row in source for value in row))
    for i in range(n):
        for j in range(i + 1, n):
            if abs(source[i][j] - source[j][i]) > sym_tol * scale:
                raise MathInvariantError(
                    "Cholesky decomposition requires a symmetric matrix",
                    reason="non_symmetric_matrix",
                    field="matrix",
                )

    lower = [[0.0] * n for _ in range(n)]
    diagonal: list[float] = []
    for i in range(n):
        for j in range(i + 1):
            correction = compensated_sum(
                lower[i][k] * lower[j][k]
                for k in range(j)
            )
            if i == j:
                radicand = source[i][i] - correction
                cutoff = pos_tol * max(1.0, abs(source[i][i]))
                if radicand <= cutoff:
                    raise MathInvariantError(
                        "matrix is not positive definite",
                        reason="non_positive_definite_matrix",
                        field="matrix",
                    )
                lower[i][j] = math.sqrt(radicand)
                diagonal.append(lower[i][j])
            else:
                divisor = lower[j][j]
                if divisor == 0.0:
                    raise MathInvariantError(
                        "Cholesky factor has zero diagonal",
                        reason="singular_matrix",
                        field="matrix",
                    )
                lower[i][j] = (source[i][j] - correction) / divisor
                if not math.isfinite(lower[i][j]):
                    raise MathInvariantError(
                        "Cholesky factor produced non-finite value",
                        reason="non_finite_result",
                        field="matrix",
                    )

    factor = tuple(tuple(row) for row in lower)
    reconstructed = tuple(
        tuple(
            compensated_sum(
                factor[i][k] * factor[j][k]
                for k in range(min(i, j) + 1)
            )
            for j in range(n)
        )
        for i in range(n)
    )
    residual = max(
        abs(reconstructed[i][j] - source[i][j])
        for i in range(n)
        for j in range(n)
    )
    minimum = min(diagonal)
    maximum = max(diagonal)
    return CholeskyReport(
        lower=factor,
        reconstruction_linf=residual,
        minimum_diagonal=minimum,
        maximum_diagonal=maximum,
        diagonal_condition_proxy=(maximum / minimum) ** 2,
    )


def solve_cholesky(
    matrix: Sequence[Sequence[Real]],
    rhs: Sequence[Real],
    *,
    symmetry_tolerance: Real = 1e-12,
    positive_tolerance: Real = 1e-14,
) -> Vector:
    report = cholesky_decompose(
        matrix,
        symmetry_tolerance=symmetry_tolerance,
        positive_tolerance=positive_tolerance,
    )
    target = finite_vector("rhs", rhs)
    n = len(report.lower)
    if len(target) != n:
        raise MathInvariantError(
            "rhs dimension mismatch",
            reason="dimension_mismatch",
            field="rhs",
        )
    lower = report.lower
    y = [0.0] * n
    for i in range(n):
        correction = compensated_sum(lower[i][j] * y[j] for j in range(i))
        y[i] = (target[i] - correction) / lower[i][i]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        correction = compensated_sum(lower[j][i] * x[j] for j in range(i + 1, n))
        x[i] = (y[i] - correction) / lower[i][i]
    return finite_vector("solution", x)


@dataclass(frozen=True, slots=True)
class QRReport:
    q: Matrix
    r: Matrix
    reconstruction_linf: float
    orthogonality_linf: float
    minimum_r_diagonal: float


def qr_decompose(
    matrix: Sequence[Sequence[Real]],
    *,
    rank_tolerance: Real = 1e-12,
) -> QRReport:
    source = finite_matrix("matrix", matrix)
    rows = len(source)
    columns = len(source[0])
    if rows < columns:
        raise MathInvariantError(
            "thin QR requires rows >= columns",
            reason="underdetermined_matrix",
            field="matrix",
        )
    tolerance = positive_scalar("rank_tolerance", rank_tolerance)
    source_columns = [list(column) for column in transpose(source)]
    q_columns: list[Vector] = []
    r = [[0.0] * columns for _ in range(columns)]

    for column_index in range(columns):
        vector = tuple(source_columns[column_index])
        work = vector
        for basis_index, basis in enumerate(q_columns):
            coefficient = dot(basis, work)
            r[basis_index][column_index] = coefficient
            work = tuple(
                value - coefficient * direction
                for value, direction in zip(work, basis)
            )
        # One deterministic re-orthogonalization pass improves the reference
        # contract without hiding loss of rank.
        for basis_index, basis in enumerate(q_columns):
            correction = dot(basis, work)
            r[basis_index][column_index] += correction
            work = tuple(
                value - correction * direction
                for value, direction in zip(work, basis)
            )
        norm = l2_norm(work)
        scale = max(1.0, l2_norm(vector))
        if norm <= tolerance * scale:
            raise MathInvariantError(
                "matrix is rank deficient under QR tolerance",
                reason="rank_deficient_matrix",
                field="matrix",
            )
        r[column_index][column_index] = norm
        q_columns.append(tuple(value / norm for value in work))

    q = tuple(
        tuple(q_columns[column][row] for column in range(columns))
        for row in range(rows)
    )
    r_matrix = tuple(tuple(row) for row in r)
    reconstructed = tuple(
        tuple(
            compensated_sum(q[row][k] * r_matrix[k][column] for k in range(columns))
            for column in range(columns)
        )
        for row in range(rows)
    )
    reconstruction_error = max(
        abs(reconstructed[i][j] - source[i][j])
        for i in range(rows)
        for j in range(columns)
    )
    orthogonality_error = 0.0
    for i in range(columns):
        for j in range(columns):
            target = 1.0 if i == j else 0.0
            orthogonality_error = max(
                orthogonality_error,
                abs(dot(q_columns[i], q_columns[j]) - target),
            )
    return QRReport(
        q=q,
        r=r_matrix,
        reconstruction_linf=reconstruction_error,
        orthogonality_linf=orthogonality_error,
        minimum_r_diagonal=min(abs(r[i][i]) for i in range(columns)),
    )


@dataclass(frozen=True, slots=True)
class LeastSquaresReport:
    solution: Vector
    residual_l2: float
    residual_linf: float
    rank: int
    normal_equation_residual_linf: float


def least_squares(
    matrix: Sequence[Sequence[Real]],
    rhs: Sequence[Real],
    *,
    rank_tolerance: Real = 1e-12,
) -> LeastSquaresReport:
    source = finite_matrix("matrix", matrix)
    target = finite_vector("rhs", rhs)
    rows = len(source)
    columns = len(source[0])
    if len(target) != rows:
        raise MathInvariantError(
            "least-squares rhs dimension mismatch",
            reason="dimension_mismatch",
            field="rhs",
        )
    qr = qr_decompose(source, rank_tolerance=rank_tolerance)
    q_columns = transpose(qr.q)
    transformed = tuple(dot(column, target) for column in q_columns)

    solution = [0.0] * columns
    for row in range(columns - 1, -1, -1):
        correction = compensated_sum(
            qr.r[row][column] * solution[column]
            for column in range(row + 1, columns)
        )
        solution[row] = (transformed[row] - correction) / qr.r[row][row]
    result = finite_vector("solution", solution)
    prediction = matvec(source, result)
    residual = tuple(got - expected for got, expected in zip(prediction, target))
    residual_l2 = l2_norm(residual)
    residual_linf = max(abs(value) for value in residual)
    normal_residual = tuple(
        dot(column, residual)
        for column in transpose(source)
    )
    return LeastSquaresReport(
        solution=result,
        residual_l2=residual_l2,
        residual_linf=residual_linf,
        rank=columns,
        normal_equation_residual_linf=max(abs(value) for value in normal_residual),
    )
