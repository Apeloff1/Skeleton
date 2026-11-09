"""Orthonormal Haar and Walsh-Hadamard transform references."""
from __future__ import annotations

import math
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Vector, finite_vector


_INV_SQRT_TWO = 1.0 / math.sqrt(2.0)


def _power_of_two(values: Sequence[Real], name: str) -> Vector:
    source = finite_vector(name, values)
    size = len(source)
    if size & (size - 1):
        raise MathInvariantError(
            f"{name} length must be a power of two",
            reason="invalid_transform_length",
            field=name,
        )
    return source


def haar_transform(values: Sequence[Real]) -> Vector:
    source = list(_power_of_two(values, "values"))
    length = len(source)
    scratch = [0.0] * length
    while length > 1:
        half = length // 2
        for index in range(half):
            left = source[2 * index]
            right = source[2 * index + 1]
            scratch[index] = (left + right) * _INV_SQRT_TWO
            scratch[half + index] = (left - right) * _INV_SQRT_TWO
        source[:length] = scratch[:length]
        length = half
    return tuple(source)


def inverse_haar_transform(coefficients: Sequence[Real]) -> Vector:
    source = list(_power_of_two(coefficients, "coefficients"))
    length = 1
    scratch = [0.0] * len(source)
    while length < len(source):
        for index in range(length):
            average = source[index]
            detail = source[length + index]
            scratch[2 * index] = (average + detail) * _INV_SQRT_TWO
            scratch[2 * index + 1] = (average - detail) * _INV_SQRT_TWO
        source[: 2 * length] = scratch[: 2 * length]
        length *= 2
    return tuple(source)


def hadamard_transform(values: Sequence[Real]) -> Vector:
    source = list(_power_of_two(values, "values"))
    step = 1
    while step < len(source):
        block = step * 2
        for start in range(0, len(source), block):
            for offset in range(step):
                left = source[start + offset]
                right = source[start + offset + step]
                source[start + offset] = (left + right) * _INV_SQRT_TWO
                source[start + offset + step] = (left - right) * _INV_SQRT_TWO
        step = block
    return tuple(source)


def inverse_hadamard_transform(coefficients: Sequence[Real]) -> Vector:
    # The normalized Walsh-Hadamard matrix is symmetric and self-inverse.
    return hadamard_transform(coefficients)
