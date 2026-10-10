"""Residual-carrying scalar and SPD iterative solver references."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Callable, Sequence

from .contracts import MathInvariantError, Matrix, Vector, finite_matrix, finite_scalar, finite_vector, positive_scalar
from .linear import dot, l2_norm, matvec


ScalarFunction = Callable[[float], Real]


@dataclass(frozen=True, slots=True)
class RootReport:
    root: float
    function_value: float
    bracket: tuple[float, float]
    iterations: int
    converged: bool
    newton_steps: int = 0
    bisection_steps: int = 0


def _value(function: ScalarFunction, x: float, *, name: str = "function") -> float:
    return finite_scalar(name, function(x))


def bisection_root(
    function: ScalarFunction,
    left: Real,
    right: Real,
    *,
    x_tolerance: Real = 1e-12,
    function_tolerance: Real = 1e-12,
    max_iterations: int = 200,
) -> RootReport:
    a = finite_scalar("left", left)
    b = finite_scalar("right", right)
    if b <= a:
        raise MathInvariantError(
            "root bracket must satisfy left < right",
            reason="invalid_bracket",
            field="bracket",
        )
    xtol = positive_scalar("x_tolerance", x_tolerance)
    ftol = positive_scalar("function_tolerance", function_tolerance)
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations < 1:
        raise MathInvariantError(
            "max_iterations must be a positive integer",
            reason="invalid_iteration_limit",
            field="max_iterations",
        )
    fa = _value(function, a)
    fb = _value(function, b)
    if abs(fa) <= ftol:
        return RootReport(a, fa, (a, b), 0, True, bisection_steps=0)
    if abs(fb) <= ftol:
        return RootReport(b, fb, (a, b), 0, True, bisection_steps=0)
    if fa * fb > 0.0:
        raise MathInvariantError(
            "bisection requires a sign-changing bracket",
            reason="root_not_bracketed",
            field="bracket",
        )

    midpoint = (a + b) * 0.5
    fm = _value(function, midpoint)
    for iteration in range(1, max_iterations + 1):
        midpoint = (a + b) * 0.5
        fm = _value(function, midpoint)
        if abs(fm) <= ftol or (b - a) * 0.5 <= xtol:
            return RootReport(
                midpoint,
                fm,
                (a, b),
                iteration,
                True,
                bisection_steps=iteration,
            )
        if fa * fm <= 0.0:
            b, fb = midpoint, fm
        else:
            a, fa = midpoint, fm
    return RootReport(
        midpoint,
        fm,
        (a, b),
        max_iterations,
        False,
        bisection_steps=max_iterations,
    )


def bracketed_newton_root(
    function: ScalarFunction,
    derivative: ScalarFunction,
    left: Real,
    right: Real,
    *,
    initial: Real | None = None,
    x_tolerance: Real = 1e-12,
    function_tolerance: Real = 1e-12,
    derivative_floor: Real = 1e-14,
    max_iterations: int = 100,
) -> RootReport:
    a = finite_scalar("left", left)
    b = finite_scalar("right", right)
    if b <= a:
        raise MathInvariantError(
            "root bracket must satisfy left < right",
            reason="invalid_bracket",
            field="bracket",
        )
    xtol = positive_scalar("x_tolerance", x_tolerance)
    ftol = positive_scalar("function_tolerance", function_tolerance)
    dfloor = positive_scalar("derivative_floor", derivative_floor)
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations < 1:
        raise MathInvariantError(
            "max_iterations must be a positive integer",
            reason="invalid_iteration_limit",
            field="max_iterations",
        )
    fa = _value(function, a)
    fb = _value(function, b)
    if fa * fb > 0.0:
        raise MathInvariantError(
            "Newton safeguard requires a sign-changing bracket",
            reason="root_not_bracketed",
            field="bracket",
        )
    x = (a + b) * 0.5 if initial is None else finite_scalar("initial", initial)
    if not a <= x <= b:
        raise MathInvariantError(
            "initial root estimate must lie inside the bracket",
            reason="invalid_initial_value",
            field="initial",
        )

    newton_steps = 0
    bisection_steps = 0
    fx = _value(function, x)
    for iteration in range(1, max_iterations + 1):
        if abs(fx) <= ftol or (b - a) * 0.5 <= xtol:
            return RootReport(
                x, fx, (a, b), iteration - 1, True, newton_steps, bisection_steps
            )

        dfx = _value(derivative, x, name="derivative")
        use_newton = abs(dfx) > dfloor
        candidate = x - fx / dfx if use_newton else math.nan
        if not use_newton or not math.isfinite(candidate) or not a < candidate < b:
            candidate = (a + b) * 0.5
            bisection_steps += 1
        else:
            newton_steps += 1

        fc = _value(function, candidate)
        if fa * fc <= 0.0:
            b, fb = candidate, fc
        else:
            a, fa = candidate, fc
        x, fx = candidate, fc

    return RootReport(
        x, fx, (a, b), max_iterations, False, newton_steps, bisection_steps
    )


@dataclass(frozen=True, slots=True)
class ConjugateGradientReport:
    solution: Vector
    residual_l2: float
    iterations: int
    converged: bool


def _symmetric_square(
    matrix: Sequence[Sequence[Real]],
    *,
    symmetry_tolerance: Real,
) -> Matrix:
    source = finite_matrix("matrix", matrix)
    n = len(source)
    if len(source[0]) != n:
        raise MathInvariantError(
            "conjugate gradient requires a square matrix",
            reason="non_square_matrix",
            field="matrix",
        )
    tolerance = positive_scalar("symmetry_tolerance", symmetry_tolerance)
    scale = max(1.0, max(abs(value) for row in source for value in row))
    for i in range(n):
        for j in range(i + 1, n):
            if abs(source[i][j] - source[j][i]) > tolerance * scale:
                raise MathInvariantError(
                    "conjugate gradient requires a symmetric matrix",
                    reason="non_symmetric_matrix",
                    field="matrix",
                )
    return source


def conjugate_gradient(
    matrix: Sequence[Sequence[Real]],
    rhs: Sequence[Real],
    *,
    initial: Sequence[Real] | None = None,
    absolute_tolerance: Real = 1e-12,
    relative_tolerance: Real = 1e-10,
    symmetry_tolerance: Real = 1e-12,
    max_iterations: int | None = None,
) -> ConjugateGradientReport:
    source = _symmetric_square(matrix, symmetry_tolerance=symmetry_tolerance)
    b = finite_vector("rhs", rhs)
    n = len(source)
    if len(b) != n:
        raise MathInvariantError(
            "rhs dimension mismatch",
            reason="dimension_mismatch",
            field="rhs",
        )
    if initial is None:
        x = tuple(0.0 for _ in range(n))
    else:
        x = finite_vector("initial", initial)
        if len(x) != n:
            raise MathInvariantError(
                "initial dimension mismatch",
                reason="dimension_mismatch",
                field="initial",
            )
    abs_tol = positive_scalar("absolute_tolerance", absolute_tolerance)
    rel_tol = positive_scalar("relative_tolerance", relative_tolerance)
    limit = max(1, 10 * n) if max_iterations is None else max_iterations
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise MathInvariantError(
            "max_iterations must be a positive integer",
            reason="invalid_iteration_limit",
            field="max_iterations",
        )

    ax = matvec(source, x)
    residual = tuple(target - value for target, value in zip(b, ax))
    p = residual
    residual_sq = dot(residual, residual)
    target_norm = max(abs_tol, rel_tol * l2_norm(b))
    residual_norm = math.sqrt(max(0.0, residual_sq))
    if residual_norm <= target_norm:
        return ConjugateGradientReport(x, residual_norm, 0, True)

    for iteration in range(1, limit + 1):
        ap = matvec(source, p)
        curvature = dot(p, ap)
        if curvature <= 0.0 or not math.isfinite(curvature):
            raise MathInvariantError(
                "matrix is not positive definite along the search direction",
                reason="non_positive_definite_matrix",
                field="matrix",
            )
        alpha = residual_sq / curvature
        x = tuple(value + alpha * direction for value, direction in zip(x, p))
        residual = tuple(value - alpha * image for value, image in zip(residual, ap))
        next_sq = dot(residual, residual)
        residual_norm = math.sqrt(max(0.0, next_sq))
        if residual_norm <= target_norm:
            return ConjugateGradientReport(
                finite_vector("solution", x),
                residual_norm,
                iteration,
                True,
            )
        beta = next_sq / residual_sq
        p = tuple(value + beta * direction for value, direction in zip(residual, p))
        residual_sq = next_sq

    return ConjugateGradientReport(
        finite_vector("solution", x),
        residual_norm,
        limit,
        False,
    )
