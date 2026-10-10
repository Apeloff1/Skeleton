"""Hyper-dual numbers for exact small-problem second-order derivative oracles."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Callable, Sequence

from .contracts import MathInvariantError, Matrix, Vector, finite_scalar, finite_vector


@dataclass(frozen=True, slots=True)
class HyperDual:
    value: float
    eps1: float = 0.0
    eps2: float = 0.0
    eps12: float = 0.0

    def __post_init__(self) -> None:
        for name in ("value", "eps1", "eps2", "eps12"):
            object.__setattr__(self, name, finite_scalar(name, getattr(self, name)))

    @staticmethod
    def constant(value: Real) -> "HyperDual":
        return HyperDual(finite_scalar("value", value))

    def _coerce(self, other: "HyperDual | Real") -> "HyperDual":
        return other if isinstance(other, HyperDual) else HyperDual.constant(other)

    def __add__(self, other: "HyperDual | Real") -> "HyperDual":
        right = self._coerce(other)
        return HyperDual(
            self.value + right.value,
            self.eps1 + right.eps1,
            self.eps2 + right.eps2,
            self.eps12 + right.eps12,
        )

    __radd__ = __add__

    def __neg__(self) -> "HyperDual":
        return HyperDual(-self.value, -self.eps1, -self.eps2, -self.eps12)

    def __sub__(self, other: "HyperDual | Real") -> "HyperDual":
        return self + (-self._coerce(other))

    def __rsub__(self, other: Real) -> "HyperDual":
        return self._coerce(other) - self

    def __mul__(self, other: "HyperDual | Real") -> "HyperDual":
        right = self._coerce(other)
        return HyperDual(
            self.value * right.value,
            self.eps1 * right.value + self.value * right.eps1,
            self.eps2 * right.value + self.value * right.eps2,
            self.eps12 * right.value
            + self.eps1 * right.eps2
            + self.eps2 * right.eps1
            + self.value * right.eps12,
        )

    __rmul__ = __mul__

    def __pow__(self, exponent: Real) -> "HyperDual":
        power = finite_scalar("exponent", exponent)
        x = self.value
        if x < 0.0 and not power.is_integer():
            raise MathInvariantError(
                "fractional hyper-dual powers require non-negative base",
                reason="domain_error",
                field="value",
            )
        if x == 0.0 and power < 2.0:
            if power == 1.0:
                return self
            raise MathInvariantError(
                "hyper-dual power has singular second derivative at zero",
                reason="domain_error",
                field="value",
            )
        value = x**power
        first = power * x ** (power - 1.0) if power != 0.0 else 0.0
        second = (
            power * (power - 1.0) * x ** (power - 2.0)
            if power not in {0.0, 1.0}
            else 0.0
        )
        return _compose(self, value, first, second)

    def reciprocal(self) -> "HyperDual":
        if self.value == 0.0:
            raise MathInvariantError(
                "hyper-dual division by zero",
                reason="division_by_zero",
                field="value",
            )
        x = self.value
        return _compose(self, 1.0 / x, -1.0 / (x * x), 2.0 / (x**3))

    def __truediv__(self, other: "HyperDual | Real") -> "HyperDual":
        return self * self._coerce(other).reciprocal()

    def __rtruediv__(self, other: Real) -> "HyperDual":
        return self._coerce(other) / self


def _compose(source: HyperDual, value: float, first: float, second: float) -> HyperDual:
    return HyperDual(
        value,
        first * source.eps1,
        first * source.eps2,
        first * source.eps12 + second * source.eps1 * source.eps2,
    )


def exp(value: HyperDual) -> HyperDual:
    result = math.exp(value.value)
    return _compose(value, result, result, result)


def log(value: HyperDual) -> HyperDual:
    if value.value <= 0.0:
        raise MathInvariantError(
            "hyper-dual logarithm requires positive input",
            reason="domain_error",
            field="value",
        )
    x = value.value
    return _compose(value, math.log(x), 1.0 / x, -1.0 / (x * x))


def sin(value: HyperDual) -> HyperDual:
    return _compose(value, math.sin(value.value), math.cos(value.value), -math.sin(value.value))


def cos(value: HyperDual) -> HyperDual:
    return _compose(value, math.cos(value.value), -math.sin(value.value), -math.cos(value.value))


def sqrt(value: HyperDual) -> HyperDual:
    if value.value <= 0.0:
        raise MathInvariantError(
            "hyper-dual square root requires positive input for second derivative",
            reason="domain_error",
            field="value",
        )
    root = math.sqrt(value.value)
    return _compose(value, root, 0.5 / root, -0.25 / (value.value * root))


def tanh(value: HyperDual) -> HyperDual:
    result = math.tanh(value.value)
    first = 1.0 - result * result
    second = -2.0 * result * first
    return _compose(value, result, first, second)


ScalarHyperFunction = Callable[[tuple[HyperDual, ...]], HyperDual]


@dataclass(frozen=True, slots=True)
class HyperDualHessianReport:
    value: float
    gradient: Vector
    hessian: Matrix
    symmetry_linf: float
    evaluations: int


def value_gradient_hessian(
    function: ScalarHyperFunction,
    point: Sequence[Real],
) -> HyperDualHessianReport:
    center = finite_vector("point", point)
    n = len(center)
    hessian = [[0.0] * n for _ in range(n)]
    gradient = [0.0] * n
    function_value: float | None = None
    evaluations = 0

    for i in range(n):
        for j in range(n):
            variables = tuple(
                HyperDual(
                    value,
                    1.0 if index == i else 0.0,
                    1.0 if index == j else 0.0,
                    0.0,
                )
                for index, value in enumerate(center)
            )
            result = function(variables)
            if not isinstance(result, HyperDual):
                raise MathInvariantError(
                    "hyper-dual function must return HyperDual",
                    reason="invalid_return_type",
                    field="function",
                )
            evaluations += 1
            if function_value is None:
                function_value = result.value
            elif result.value != function_value:
                raise MathInvariantError(
                    "hyper-dual function value changed across derivative seeds",
                    reason="non_deterministic_function",
                    field="function",
                )
            if j == 0:
                gradient[i] = result.eps1
            hessian[i][j] = result.eps12

    symmetry = max(
        abs(hessian[i][j] - hessian[j][i])
        for i in range(n)
        for j in range(n)
    )
    return HyperDualHessianReport(
        value=0.0 if function_value is None else function_value,
        gradient=tuple(gradient),
        hessian=tuple(tuple(row) for row in hessian),
        symmetry_linf=symmetry,
        evaluations=evaluations,
    )


def second_derivative(
    function: Callable[[HyperDual], HyperDual],
    x: Real,
) -> float:
    point = finite_scalar("x", x)
    result = function(HyperDual(point, 1.0, 1.0, 0.0))
    if not isinstance(result, HyperDual):
        raise MathInvariantError(
            "hyper-dual function must return HyperDual",
            reason="invalid_return_type",
            field="function",
        )
    return result.eps12
