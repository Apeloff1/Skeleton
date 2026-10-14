"""Discrete transform, convolution, and autocorrelation reference routines."""
from __future__ import annotations

import cmath
import math
from numbers import Real
from typing import Iterable, Sequence

from .contracts import MathInvariantError, Vector, finite_scalar, finite_vector
from .numerics import compensated_sum, stable_mean


def _complex_sequence(values: Sequence[complex | Real] | Iterable[complex | Real]) -> tuple[complex, ...]:
    output: list[complex] = []
    for index, value in enumerate(values):
        if isinstance(value, bool) or not isinstance(value, (int, float, complex)):
            raise MathInvariantError(
                "transform values must be numeric",
                reason="invalid_numeric_type",
                field=f"values[{index}]",
            )
        item = complex(value)
        if not math.isfinite(item.real) or not math.isfinite(item.imag):
            raise MathInvariantError(
                "transform values must be finite",
                reason="non_finite_value",
                field=f"values[{index}]",
            )
        output.append(item)
    if not output:
        raise MathInvariantError(
            "transform input must not be empty",
            reason="empty_vector",
            field="values",
        )
    return tuple(output)


def dft(values: Sequence[complex | Real]) -> tuple[complex, ...]:
    source = _complex_sequence(values)
    n = len(source)
    output = []
    for frequency in range(n):
        output.append(
            sum(
                value * cmath.exp(-2j * math.pi * frequency * index / n)
                for index, value in enumerate(source)
            )
        )
    return tuple(output)


def inverse_dft(values: Sequence[complex | Real]) -> tuple[complex, ...]:
    source = _complex_sequence(values)
    n = len(source)
    output = []
    for index in range(n):
        output.append(
            sum(
                value * cmath.exp(2j * math.pi * frequency * index / n)
                for frequency, value in enumerate(source)
            ) / n
        )
    return tuple(output)


def fft_radix2(values: Sequence[complex | Real]) -> tuple[complex, ...]:
    source = _complex_sequence(values)
    n = len(source)
    if n & (n - 1):
        raise MathInvariantError(
            "radix-2 FFT length must be a power of two",
            reason="invalid_fft_length",
            field="values",
        )

    def recurse(items: tuple[complex, ...]) -> tuple[complex, ...]:
        size = len(items)
        if size == 1:
            return items
        even = recurse(items[0::2])
        odd = recurse(items[1::2])
        first: list[complex] = []
        second: list[complex] = []
        for index in range(size // 2):
            twiddle = cmath.exp(-2j * math.pi * index / size) * odd[index]
            first.append(even[index] + twiddle)
            second.append(even[index] - twiddle)
        return tuple(first + second)

    return recurse(source)


def inverse_fft_radix2(values: Sequence[complex | Real]) -> tuple[complex, ...]:
    source = _complex_sequence(values)
    transformed = fft_radix2(tuple(value.conjugate() for value in source))
    n = len(source)
    return tuple(value.conjugate() / n for value in transformed)


def convolution(
    left: Sequence[Real],
    right: Sequence[Real],
) -> Vector:
    a = finite_vector("left", left)
    b = finite_vector("right", right)
    output = []
    for index in range(len(a) + len(b) - 1):
        output.append(
            compensated_sum(
                a[left_index] * b[index - left_index]
                for left_index in range(max(0, index - len(b) + 1), min(len(a) - 1, index) + 1)
            )
        )
    return tuple(output)


def autocorrelation(
    values: Sequence[Real],
    *,
    max_lag: int | None = None,
    center: bool = True,
    normalized: bool = False,
) -> Vector:
    observations = finite_vector("values", values)
    limit = len(observations) - 1 if max_lag is None else max_lag
    if isinstance(limit, bool) or not isinstance(limit, int) or not 0 <= limit < len(observations):
        raise MathInvariantError(
            "max_lag must be an integer in [0, len(values)-1]",
            reason="invalid_lag",
            field="max_lag",
        )
    mean = stable_mean(observations) if center else 0.0
    centered = tuple(value - mean for value in observations)
    result = []
    for lag in range(limit + 1):
        result.append(
            compensated_sum(
                centered[index] * centered[index + lag]
                for index in range(len(centered) - lag)
            )
        )
    if normalized:
        denominator = result[0]
        if denominator == 0.0:
            raise MathInvariantError(
                "normalized autocorrelation requires non-zero energy",
                reason="zero_variance",
                field="values",
            )
        return tuple(value / denominator for value in result)
    return tuple(result)
