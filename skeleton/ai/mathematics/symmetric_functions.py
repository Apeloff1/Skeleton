"""Spectral functions of real symmetric matrices with explicit domain evidence."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Callable, Sequence

from .contracts import MathInvariantError, Matrix, Vector, finite_matrix, positive_scalar
from .eigensystems import symmetric_eigensystem
from .numerics import compensated_sum


@dataclass(frozen=True, slots=True)
class SymmetricMatrixFunctionReport:
    value: Matrix
    source_eigenvalues: Vector
    transformed_eigenvalues: Vector
    symmetry_linf: float
    spectral_reconstruction_linf: float
    function_name: str


def _symmetric_function(
    matrix: Sequence[Sequence[Real]],
    function: Callable[[float], float],
    *,
    function_name: str,
    domain: str,
    tolerance: Real = 1e-12,
) -> SymmetricMatrixFunctionReport:
    source = finite_matrix("matrix", matrix)
    n = len(source)
    if len(source[0]) != n:
        raise MathInvariantError(
            "symmetric matrix function requires a square matrix",
            reason="non_square_matrix",
            field="matrix",
        )
    tol = positive_scalar("tolerance", tolerance)
    eig = symmetric_eigensystem(source, tolerance=tol)
    scale = max(1.0, max(abs(value) for value in eig.eigenvalues))
    transformed: list[float] = []
    cleaned: list[float] = []
    for index, eigenvalue in enumerate(eig.eigenvalues):
        value = eigenvalue
        if domain == "nonnegative":
            if value < -tol * scale:
                raise MathInvariantError(
                    f"{function_name} requires positive-semidefinite spectrum",
                    reason="matrix_function_domain_error",
                    field=f"eigenvalues[{index}]",
                )
            value = max(0.0, value)
        elif domain == "positive":
            if value <= tol * scale:
                raise MathInvariantError(
                    f"{function_name} requires positive-definite spectrum",
                    reason="matrix_function_domain_error",
                    field=f"eigenvalues[{index}]",
                )
        cleaned.append(value)
        transformed_value = function(value)
        if not math.isfinite(transformed_value):
            raise MathInvariantError(
                f"{function_name} produced a non-finite eigenvalue transform",
                reason="non_finite_result",
                field=f"eigenvalues[{index}]",
            )
        transformed.append(transformed_value)

    result = tuple(
        tuple(
            compensated_sum(
                transformed[k] * eig.eigenvectors[k][i] * eig.eigenvectors[k][j]
                for k in range(n)
            )
            for j in range(n)
        )
        for i in range(n)
    )
    symmetry = max(
        abs(result[i][j] - result[j][i])
        for i in range(n)
        for j in range(n)
    )
    reconstructed = tuple(
        tuple(
            compensated_sum(
                cleaned[k] * eig.eigenvectors[k][i] * eig.eigenvectors[k][j]
                for k in range(n)
            )
            for j in range(n)
        )
        for i in range(n)
    )
    reconstruction = max(
        abs(reconstructed[i][j] - source[i][j])
        for i in range(n)
        for j in range(n)
    )
    return SymmetricMatrixFunctionReport(
        value=result,
        source_eigenvalues=eig.eigenvalues,
        transformed_eigenvalues=tuple(transformed),
        symmetry_linf=symmetry,
        spectral_reconstruction_linf=reconstruction,
        function_name=function_name,
    )


def symmetric_matrix_sqrt(
    matrix: Sequence[Sequence[Real]],
    *,
    tolerance: Real = 1e-12,
) -> SymmetricMatrixFunctionReport:
    return _symmetric_function(
        matrix,
        math.sqrt,
        function_name="matrix_sqrt",
        domain="nonnegative",
        tolerance=tolerance,
    )


def symmetric_matrix_inverse_sqrt(
    matrix: Sequence[Sequence[Real]],
    *,
    tolerance: Real = 1e-12,
) -> SymmetricMatrixFunctionReport:
    return _symmetric_function(
        matrix,
        lambda value: 1.0 / math.sqrt(value),
        function_name="matrix_inverse_sqrt",
        domain="positive",
        tolerance=tolerance,
    )


def symmetric_matrix_log(
    matrix: Sequence[Sequence[Real]],
    *,
    tolerance: Real = 1e-12,
) -> SymmetricMatrixFunctionReport:
    return _symmetric_function(
        matrix,
        math.log,
        function_name="matrix_log",
        domain="positive",
        tolerance=tolerance,
    )


def symmetric_matrix_exp(
    matrix: Sequence[Sequence[Real]],
    *,
    tolerance: Real = 1e-12,
) -> SymmetricMatrixFunctionReport:
    return _symmetric_function(
        matrix,
        math.exp,
        function_name="matrix_exp",
        domain="all",
        tolerance=tolerance,
    )
