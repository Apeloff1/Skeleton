"""Linear control-system reference mathematics without execution authority."""
from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Matrix, finite_matrix, positive_scalar
from .eigensystems import symmetric_eigensystem
from .linear import matmul, transpose
from .matrix_equations import solve_continuous_lyapunov
from .matrix_exponential import MatrixExponentialReport
from .matrix_functions import matrix_exponential
from .numerics import compensated_sum
from .svd import singular_value_decomposition


def _square(matrix: Sequence[Sequence[Real]], name: str) -> Matrix:
    source = finite_matrix(name, matrix)
    if len(source) != len(source[0]):
        raise MathInvariantError(
            f"{name} must be square",
            reason="non_square_matrix",
            field=name,
        )
    return source


def controllability_matrix(
    system: Sequence[Sequence[Real]],
    input_matrix: Sequence[Sequence[Real]],
) -> Matrix:
    a = _square(system, "system")
    b = finite_matrix("input_matrix", input_matrix)
    n = len(a)
    if len(b) != n:
        raise MathInvariantError(
            "input matrix row count must match state dimension",
            reason="dimension_mismatch",
            field="input_matrix",
        )
    blocks = [b]
    current = b
    for _ in range(1, n):
        current = matmul(a, current)
        blocks.append(current)
    return tuple(
        tuple(value for block in blocks for value in block[row])
        for row in range(n)
    )


def observability_matrix(
    system: Sequence[Sequence[Real]],
    output_matrix: Sequence[Sequence[Real]],
) -> Matrix:
    a = _square(system, "system")
    c = finite_matrix("output_matrix", output_matrix)
    n = len(a)
    if len(c[0]) != n:
        raise MathInvariantError(
            "output matrix column count must match state dimension",
            reason="dimension_mismatch",
            field="output_matrix",
        )
    blocks = [c]
    current = c
    for _ in range(1, n):
        current = matmul(current, a)
        blocks.append(current)
    return tuple(row for block in blocks for row in block)


@dataclass(frozen=True, slots=True)
class LinearSystemRankReport:
    rank: int
    state_dimension: int
    full_rank: bool
    smallest_nonzero_singular_value: float | None
    largest_singular_value: float | None


def controllability_report(
    system: Sequence[Sequence[Real]],
    input_matrix: Sequence[Sequence[Real]],
) -> LinearSystemRankReport:
    matrix = controllability_matrix(system, input_matrix)
    svd = singular_value_decomposition(matrix)
    values = svd.singular_values
    return LinearSystemRankReport(
        rank=svd.rank,
        state_dimension=len(matrix),
        full_rank=svd.rank == len(matrix),
        smallest_nonzero_singular_value=min(values) if values else None,
        largest_singular_value=max(values) if values else None,
    )


def observability_report(
    system: Sequence[Sequence[Real]],
    output_matrix: Sequence[Sequence[Real]],
) -> LinearSystemRankReport:
    matrix = observability_matrix(system, output_matrix)
    svd = singular_value_decomposition(matrix)
    state_dimension = len(_square(system, "system"))
    values = svd.singular_values
    return LinearSystemRankReport(
        rank=svd.rank,
        state_dimension=state_dimension,
        full_rank=svd.rank == state_dimension,
        smallest_nonzero_singular_value=min(values) if values else None,
        largest_singular_value=max(values) if values else None,
    )


@dataclass(frozen=True, slots=True)
class DiscreteLinearSystemReport:
    state_matrix: Matrix
    input_matrix: Matrix
    time_step: float
    exponential_terms: int
    squarings: int


def discretize_zero_order_hold(
    system: Sequence[Sequence[Real]],
    input_matrix: Sequence[Sequence[Real]],
    time_step: Real,
) -> DiscreteLinearSystemReport:
    a = _square(system, "system")
    b = finite_matrix("input_matrix", input_matrix)
    n = len(a)
    if len(b) != n:
        raise MathInvariantError(
            "input matrix row count must match state dimension",
            reason="dimension_mismatch",
            field="input_matrix",
        )
    dt = positive_scalar("time_step", time_step)
    inputs = len(b[0])
    augmented = []
    for row in range(n):
        augmented.append(tuple(dt * value for value in a[row]) + tuple(dt * value for value in b[row]))
    for _ in range(inputs):
        augmented.append(tuple(0.0 for _ in range(n + inputs)))
    exponential = matrix_exponential(tuple(augmented))
    value = exponential.value
    ad = tuple(tuple(value[i][j] for j in range(n)) for i in range(n))
    bd = tuple(tuple(value[i][n + j] for j in range(inputs)) for i in range(n))
    return DiscreteLinearSystemReport(
        state_matrix=ad,
        input_matrix=bd,
        time_step=dt,
        exponential_terms=exponential.taylor_terms,
        squarings=exponential.squarings,
    )


@dataclass(frozen=True, slots=True)
class GramianReport:
    gramian: Matrix
    residual_linf: float
    symmetry_linf: float
    minimum_eigenvalue: float
    maximum_eigenvalue: float
    positive_definite: bool


def _gramian_report(solution: Matrix, residual: float, symmetry: float) -> GramianReport:
    eig = symmetric_eigensystem(solution)
    minimum = min(eig.eigenvalues)
    maximum = max(eig.eigenvalues)
    scale = max(1.0, abs(maximum))
    return GramianReport(
        gramian=solution,
        residual_linf=residual,
        symmetry_linf=symmetry,
        minimum_eigenvalue=minimum,
        maximum_eigenvalue=maximum,
        positive_definite=minimum > 1e-12 * scale,
    )


def controllability_gramian(
    system: Sequence[Sequence[Real]],
    input_matrix: Sequence[Sequence[Real]],
) -> GramianReport:
    a = _square(system, "system")
    b = finite_matrix("input_matrix", input_matrix)
    if len(b) != len(a):
        raise MathInvariantError(
            "input matrix row count must match state dimension",
            reason="dimension_mismatch",
            field="input_matrix",
        )
    bt = transpose(b)
    forcing = matmul(b, bt)
    report = solve_continuous_lyapunov(a, forcing)
    return _gramian_report(report.solution, report.residual_linf, report.symmetry_linf)


def observability_gramian(
    system: Sequence[Sequence[Real]],
    output_matrix: Sequence[Sequence[Real]],
) -> GramianReport:
    a = _square(system, "system")
    c = finite_matrix("output_matrix", output_matrix)
    if len(c[0]) != len(a):
        raise MathInvariantError(
            "output matrix column count must match state dimension",
            reason="dimension_mismatch",
            field="output_matrix",
        )
    ct = transpose(c)
    forcing = matmul(ct, c)
    report = solve_continuous_lyapunov(transpose(a), forcing)
    return _gramian_report(report.solution, report.residual_linf, report.symmetry_linf)
