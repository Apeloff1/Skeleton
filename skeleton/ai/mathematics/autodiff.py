"""Forward-mode automatic differentiation for deterministic reference checks.

The dual-number engine is deliberately small and explicit.  It is an oracle for
first derivatives and Jacobians, not a training runtime or graph executor.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Callable, Sequence

from .contracts import MathInvariantError, Vector, finite_scalar, finite_vector, positive_scalar


@dataclass(frozen=True, slots=True)
class Dual:
    """A scalar value carrying one or more directional derivatives."""

    value: float
    tangent: Vector

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", finite_scalar("value", self.value))
        object.__setattr__(
            self,
            "tangent",
            finite_vector("tangent", self.tangent, allow_empty=False),
        )

    @property
    def dimensions(self) -> int:
        return len(self.tangent)

    @classmethod
    def constant(cls, value: Real, dimensions: int) -> "Dual":
        _validate_dimensions(dimensions)
        return cls(float(value), tuple(0.0 for _ in range(dimensions)))

    @classmethod
    def variable(cls, value: Real, index: int, dimensions: int) -> "Dual":
        _validate_dimensions(dimensions)
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < dimensions:
            raise MathInvariantError(
                "dual variable index is out of range",
                reason="invalid_dual_index",
                field="index",
            )
        tangent = [0.0] * dimensions
        tangent[index] = 1.0
        return cls(float(value), tuple(tangent))

    def _coerce(self, other: Real | "Dual") -> "Dual":
        if isinstance(other, Dual):
            if other.dimensions != self.dimensions:
                raise MathInvariantError(
                    "dual derivative dimensions must match",
                    reason="dimension_mismatch",
                    field="dual",
                )
            return other
        return Dual.constant(finite_scalar("operand", other), self.dimensions)

    def __add__(self, other: Real | "Dual") -> "Dual":
        rhs = self._coerce(other)
        return Dual(
            self.value + rhs.value,
            tuple(a + b for a, b in zip(self.tangent, rhs.tangent)),
        )

    def __radd__(self, other: Real | "Dual") -> "Dual":
        return self + other

    def __sub__(self, other: Real | "Dual") -> "Dual":
        rhs = self._coerce(other)
        return Dual(
            self.value - rhs.value,
            tuple(a - b for a, b in zip(self.tangent, rhs.tangent)),
        )

    def __rsub__(self, other: Real | "Dual") -> "Dual":
        return (-self) + other

    def __mul__(self, other: Real | "Dual") -> "Dual":
        rhs = self._coerce(other)
        return Dual(
            self.value * rhs.value,
            tuple(
                a * rhs.value + b * self.value
                for a, b in zip(self.tangent, rhs.tangent)
            ),
        )

    def __rmul__(self, other: Real | "Dual") -> "Dual":
        return self * other

    def __truediv__(self, other: Real | "Dual") -> "Dual":
        rhs = self._coerce(other)
        if rhs.value == 0.0:
            raise MathInvariantError(
                "dual division by zero",
                reason="division_by_zero",
                field="operand",
            )
        denominator = rhs.value * rhs.value
        return Dual(
            self.value / rhs.value,
            tuple(
                (a * rhs.value - self.value * b) / denominator
                for a, b in zip(self.tangent, rhs.tangent)
            ),
        )

    def __rtruediv__(self, other: Real | "Dual") -> "Dual":
        lhs = self._coerce(other)
        return lhs / self

    def __neg__(self) -> "Dual":
        return Dual(-self.value, tuple(-value for value in self.tangent))

    def __pow__(self, exponent: Real) -> "Dual":
        power = finite_scalar("exponent", exponent)
        if self.value < 0.0 and not power.is_integer():
            raise MathInvariantError(
                "fractional powers of negative dual values are outside the real domain",
                reason="domain_error",
                field="value",
            )
        if self.value == 0.0 and power < 1.0:
            raise MathInvariantError(
                "dual power derivative is singular at zero",
                reason="singular_derivative",
                field="value",
            )
        value = self.value ** power
        scale = power * (self.value ** (power - 1.0)) if power != 0.0 else 0.0
        return Dual(value, tuple(scale * derivative for derivative in self.tangent))


def _validate_dimensions(dimensions: int) -> None:
    if isinstance(dimensions, bool) or not isinstance(dimensions, int) or dimensions < 1:
        raise MathInvariantError(
            "dual dimensions must be a positive integer",
            reason="invalid_dual_dimensions",
            field="dimensions",
        )


def _unary(value: Dual, output: float, derivative: float) -> Dual:
    finite_scalar("output", output)
    finite_scalar("derivative", derivative)
    return Dual(output, tuple(derivative * item for item in value.tangent))


def exp(value: Dual) -> Dual:
    output = math.exp(value.value)
    return _unary(value, output, output)


def log(value: Dual) -> Dual:
    if value.value <= 0.0:
        raise MathInvariantError(
            "log requires a positive dual value",
            reason="domain_error",
            field="value",
        )
    return _unary(value, math.log(value.value), 1.0 / value.value)


def sin(value: Dual) -> Dual:
    return _unary(value, math.sin(value.value), math.cos(value.value))


def cos(value: Dual) -> Dual:
    return _unary(value, math.cos(value.value), -math.sin(value.value))


def tanh(value: Dual) -> Dual:
    output = math.tanh(value.value)
    return _unary(value, output, 1.0 - output * output)


def sqrt(value: Dual) -> Dual:
    if value.value <= 0.0:
        raise MathInvariantError(
            "sqrt derivative requires a strictly positive dual value",
            reason="domain_error",
            field="value",
        )
    output = math.sqrt(value.value)
    return _unary(value, output, 0.5 / output)


def sigmoid(value: Dual) -> Dual:
    if value.value >= 0.0:
        z = math.exp(-value.value)
        output = 1.0 / (1.0 + z)
    else:
        z = math.exp(value.value)
        output = z / (1.0 + z)
    return _unary(value, output, output * (1.0 - output))


def softplus(value: Dual) -> Dual:
    if value.value > 36.0:
        output = value.value
    elif value.value < -36.0:
        output = math.exp(value.value)
    else:
        output = math.log1p(math.exp(value.value))
    derivative = sigmoid(value).value
    return _unary(value, output, derivative)


DualFunction = Callable[[tuple[Dual, ...]], Dual]
DualVectorFunction = Callable[[tuple[Dual, ...]], Sequence[Dual]]


def value_and_gradient(function: DualFunction, point: Sequence[Real]) -> tuple[float, Vector]:
    values = finite_vector("point", point)
    dimensions = len(values)
    duals = tuple(Dual.variable(value, index, dimensions) for index, value in enumerate(values))
    result = function(duals)
    if not isinstance(result, Dual):
        raise MathInvariantError(
            "autodiff function must return Dual",
            reason="invalid_autodiff_output",
            field="function",
        )
    if result.dimensions != dimensions:
        raise MathInvariantError(
            "autodiff result derivative dimension mismatch",
            reason="dimension_mismatch",
            field="function",
        )
    return result.value, result.tangent


def gradient(function: DualFunction, point: Sequence[Real]) -> Vector:
    return value_and_gradient(function, point)[1]


def jacobian(function: DualVectorFunction, point: Sequence[Real]) -> tuple[Vector, ...]:
    values = finite_vector("point", point)
    dimensions = len(values)
    duals = tuple(Dual.variable(value, index, dimensions) for index, value in enumerate(values))
    outputs = tuple(function(duals))
    if not outputs:
        raise MathInvariantError(
            "Jacobian function must return at least one output",
            reason="empty_autodiff_output",
            field="function",
        )
    rows: list[Vector] = []
    for index, output in enumerate(outputs):
        if not isinstance(output, Dual):
            raise MathInvariantError(
                "Jacobian outputs must be Dual values",
                reason="invalid_autodiff_output",
                field=f"output[{index}]",
            )
        if output.dimensions != dimensions:
            raise MathInvariantError(
                "Jacobian derivative dimension mismatch",
                reason="dimension_mismatch",
                field=f"output[{index}]",
            )
        rows.append(output.tangent)
    return tuple(rows)


def directional_derivative(
    function: DualFunction,
    point: Sequence[Real],
    direction: Sequence[Real],
) -> float:
    values = finite_vector("point", point)
    tangent = finite_vector("direction", direction)
    if len(values) != len(tangent):
        raise MathInvariantError(
            "direction dimension mismatch",
            reason="dimension_mismatch",
            field="direction",
        )
    norm = math.hypot(*tangent)
    positive_scalar("direction_norm", norm)
    duals = tuple(Dual(value, (delta,)) for value, delta in zip(values, tangent))
    result = function(duals)
    if not isinstance(result, Dual) or result.dimensions != 1:
        raise MathInvariantError(
            "directional derivative function must return a one-direction Dual",
            reason="invalid_autodiff_output",
            field="function",
        )
    return result.tangent[0]
