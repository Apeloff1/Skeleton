"""Dense Sylvester and continuous Lyapunov equation reference solvers."""
from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Matrix, finite_matrix
from .linear import solve_linear_system, transpose
from .numerics import compensated_sum


@dataclass(frozen=True, slots=True)
class SylvesterReport:
    solution: Matrix
    residual_linf: float
    left_size: int
    right_size: int


def solve_sylvester(
    left: Sequence[Sequence[Real]],
    right: Sequence[Sequence[Real]],
    target: Sequence[Sequence[Real]],
) -> SylvesterReport:
    """Solve A X + X B = C using the explicit Kronecker linear system."""
    a = finite_matrix("left", left)
    b = finite_matrix("right", right)
    c = finite_matrix("target", target)
    m = len(a)
    n = len(b)
    if len(a[0]) != m or len(b[0]) != n:
        raise MathInvariantError(
            "Sylvester coefficient matrices must be square",
            reason="non_square_matrix",
            field="coefficients",
        )
    if len(c) != m or len(c[0]) != n:
        raise MathInvariantError(
            "Sylvester target must have shape (left size, right size)",
            reason="dimension_mismatch",
            field="target",
        )

    size = m * n
    system = [[0.0] * size for _ in range(size)]
    rhs = [0.0] * size
    for i in range(m):
        for j in range(n):
            row = i * n + j
            rhs[row] = c[i][j]
            for k in range(m):
                system[row][k * n + j] += a[i][k]
            for ell in range(n):
                system[row][i * n + ell] += b[ell][j]

    solved = solve_linear_system(
        tuple(tuple(row) for row in system),
        tuple(rhs),
    ).solution
    solution = tuple(
        tuple(solved[i * n + j] for j in range(n))
        for i in range(m)
    )
    residual = 0.0
    for i in range(m):
        for j in range(n):
            value = (
                compensated_sum(a[i][k] * solution[k][j] for k in range(m))
                + compensated_sum(solution[i][ell] * b[ell][j] for ell in range(n))
                - c[i][j]
            )
            residual = max(residual, abs(value))
    return SylvesterReport(
        solution=solution,
        residual_linf=residual,
        left_size=m,
        right_size=n,
    )


@dataclass(frozen=True, slots=True)
class LyapunovReport:
    solution: Matrix
    residual_linf: float
    symmetry_linf: float


def solve_continuous_lyapunov(
    matrix: Sequence[Sequence[Real]],
    forcing: Sequence[Sequence[Real]],
    *,
    symmetry_tolerance: Real = 1e-12,
) -> LyapunovReport:
    """Solve A X + X A^T = -Q for symmetric Q."""
    a = finite_matrix("matrix", matrix)
    q = finite_matrix("forcing", forcing)
    n = len(a)
    if len(a[0]) != n or len(q) != n or len(q[0]) != n:
        raise MathInvariantError(
            "Lyapunov inputs must be equally sized square matrices",
            reason="dimension_mismatch",
            field="lyapunov",
        )
    tolerance = float(symmetry_tolerance)
    if tolerance <= 0.0:
        raise MathInvariantError(
            "symmetry_tolerance must be positive",
            reason="invalid_tolerance",
            field="symmetry_tolerance",
        )
    scale = max(1.0, max(abs(value) for row in q for value in row))
    for i in range(n):
        for j in range(i + 1, n):
            if abs(q[i][j] - q[j][i]) > tolerance * scale:
                raise MathInvariantError(
                    "Lyapunov forcing must be symmetric",
                    reason="non_symmetric_matrix",
                    field="forcing",
                )
    target = tuple(tuple(-value for value in row) for row in q)
    report = solve_sylvester(a, transpose(a), target)
    symmetry = max(
        abs(report.solution[i][j] - report.solution[j][i])
        for i in range(n)
        for j in range(n)
    )
    return LyapunovReport(
        solution=report.solution,
        residual_linf=report.residual_linf,
        symmetry_linf=symmetry,
    )
