"""Reproducible pseudo-random, quasi-random, and Monte Carlo references."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Callable, Sequence

from .contracts import MathInvariantError, finite_scalar
from .probability import normalize_distribution


_MASK64 = (1 << 64) - 1
_HALTON_PRIMES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53)


class SplitMix64:
    """Small deterministic generator for reproducible reference experiments."""

    __slots__ = ("_state",)

    def __init__(self, seed: int = 0) -> None:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise MathInvariantError(
                "seed must be an integer",
                reason="invalid_seed",
                field="seed",
            )
        self._state = seed & _MASK64

    def next_uint64(self) -> int:
        self._state = (self._state + 0x9E3779B97F4A7C15) & _MASK64
        z = self._state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _MASK64
        return (z ^ (z >> 31)) & _MASK64

    def uniform(self) -> float:
        return (self.next_uint64() >> 11) / float(1 << 53)

    def uniform_open(self) -> float:
        return ((self.next_uint64() >> 11) + 0.5) / float(1 << 53)

    def normal(self) -> float:
        u1 = self.uniform_open()
        u2 = self.uniform_open()
        return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)

    def categorical(self, weights: Sequence[Real]) -> int:
        probabilities = normalize_distribution(weights)
        threshold = self.uniform()
        cumulative = 0.0
        for index, probability in enumerate(probabilities):
            cumulative += probability
            if threshold < cumulative:
                return index
        return len(probabilities) - 1


def systematic_resample(
    weights: Sequence[Real],
    count: int,
    *,
    seed: int = 0,
) -> tuple[int, ...]:
    probabilities = normalize_distribution(weights)
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise MathInvariantError(
            "resample count must be a positive integer",
            reason="invalid_sample_count",
            field="count",
        )
    rng = SplitMix64(seed)
    offset = rng.uniform() / count
    output: list[int] = []
    cumulative = probabilities[0]
    index = 0
    for sample_index in range(count):
        threshold = offset + sample_index / count
        while threshold > cumulative and index < len(probabilities) - 1:
            index += 1
            cumulative += probabilities[index]
        output.append(index)
    return tuple(output)


def radical_inverse(index: int, base: int) -> float:
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        raise MathInvariantError(
            "radical-inverse index must be a non-negative integer",
            reason="invalid_sequence_index",
            field="index",
        )
    if isinstance(base, bool) or not isinstance(base, int) or base < 2:
        raise MathInvariantError(
            "radical-inverse base must be an integer >= 2",
            reason="invalid_sequence_base",
            field="base",
        )
    inverse = 1.0 / base
    factor = inverse
    result = 0.0
    value = index
    while value:
        value, digit = divmod(value, base)
        result += digit * factor
        factor *= inverse
    return result


def halton_point(index: int, dimensions: int) -> tuple[float, ...]:
    if isinstance(index, bool) or not isinstance(index, int) or index < 1:
        raise MathInvariantError(
            "Halton index must be a positive integer",
            reason="invalid_sequence_index",
            field="index",
        )
    if (
        isinstance(dimensions, bool)
        or not isinstance(dimensions, int)
        or not 1 <= dimensions <= len(_HALTON_PRIMES)
    ):
        raise MathInvariantError(
            f"Halton dimensions must be in [1, {len(_HALTON_PRIMES)}]",
            reason="invalid_dimension",
            field="dimensions",
        )
    return tuple(
        radical_inverse(index, base)
        for base in _HALTON_PRIMES[:dimensions]
    )


@dataclass(frozen=True, slots=True)
class MonteCarloReport:
    estimate: float
    sample_variance: float
    standard_error: float
    samples: int
    dimensions: int
    seed: int


def monte_carlo_unit_cube(
    function: Callable[[tuple[float, ...]], Real],
    *,
    dimensions: int,
    samples: int,
    seed: int = 0,
) -> MonteCarloReport:
    if isinstance(dimensions, bool) or not isinstance(dimensions, int) or dimensions < 1:
        raise MathInvariantError(
            "dimensions must be a positive integer",
            reason="invalid_dimension",
            field="dimensions",
        )
    if isinstance(samples, bool) or not isinstance(samples, int) or samples < 2:
        raise MathInvariantError(
            "Monte Carlo requires at least two samples",
            reason="invalid_sample_count",
            field="samples",
        )
    rng = SplitMix64(seed)
    mean = 0.0
    m2 = 0.0
    for count in range(1, samples + 1):
        point = tuple(rng.uniform() for _ in range(dimensions))
        value = finite_scalar("sample_value", function(point))
        delta = value - mean
        mean += delta / count
        m2 += delta * (value - mean)
    variance = max(0.0, m2 / (samples - 1))
    return MonteCarloReport(
        estimate=mean,
        sample_variance=variance,
        standard_error=math.sqrt(variance / samples),
        samples=samples,
        dimensions=dimensions,
        seed=seed,
    )
