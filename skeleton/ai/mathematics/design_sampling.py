"""Deterministic Latin-hypercube and space-filling design references."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Vector, finite_scalar
from .sampling import SplitMix64
from .numerics import compensated_sum


def _permutation(size: int, rng: SplitMix64) -> list[int]:
    values = list(range(size))
    for index in range(size - 1, 0, -1):
        swap = rng.next_uint64() % (index + 1)
        values[index], values[swap] = values[swap], values[index]
    return values


@dataclass(frozen=True, slots=True)
class SpaceFillingDesignReport:
    points: tuple[Vector, ...]
    samples: int
    dimensions: int
    seed: int
    centered: bool
    minimum_pairwise_distance: float
    centered_l2_discrepancy: float


def latin_hypercube(
    samples: int,
    dimensions: int,
    *,
    seed: int = 0,
    centered: bool = False,
) -> SpaceFillingDesignReport:
    if isinstance(samples, bool) or not isinstance(samples, int) or samples < 2:
        raise MathInvariantError(
            "Latin hypercube requires at least two samples",
            reason="invalid_sample_count",
            field="samples",
        )
    if isinstance(dimensions, bool) or not isinstance(dimensions, int) or dimensions < 1:
        raise MathInvariantError(
            "Latin hypercube dimensions must be a positive integer",
            reason="invalid_dimension",
            field="dimensions",
        )
    rng = SplitMix64(seed)
    coordinates = [[0.0] * dimensions for _ in range(samples)]
    for dimension in range(dimensions):
        permutation = _permutation(samples, rng)
        for row in range(samples):
            offset = 0.5 if centered else rng.uniform()
            coordinates[row][dimension] = (permutation[row] + offset) / samples
    points = tuple(tuple(row) for row in coordinates)
    minimum = math.inf
    for i in range(samples):
        for j in range(i + 1, samples):
            distance = math.sqrt(
                compensated_sum((points[i][axis] - points[j][axis]) ** 2 for axis in range(dimensions))
            )
            minimum = min(minimum, distance)
    discrepancy = centered_l2_discrepancy(points)
    return SpaceFillingDesignReport(
        points=points,
        samples=samples,
        dimensions=dimensions,
        seed=seed,
        centered=centered,
        minimum_pairwise_distance=minimum,
        centered_l2_discrepancy=discrepancy,
    )


def centered_l2_discrepancy(points: Sequence[Sequence[Real]]) -> float:
    if not points:
        raise MathInvariantError(
            "discrepancy requires at least one point",
            reason="empty_sample_set",
            field="points",
        )
    clean = []
    for row, point in enumerate(points):
        values = tuple(finite_scalar(f"points[{row}][{axis}]", value) for axis, value in enumerate(point))
        if any(value < 0.0 or value > 1.0 for value in values):
            raise MathInvariantError(
                "discrepancy points must lie in the unit cube",
                reason="sample_out_of_bounds",
                field=f"points[{row}]",
            )
        clean.append(values)
    dimensions = len(clean[0])
    if dimensions < 1 or any(len(point) != dimensions for point in clean):
        raise MathInvariantError(
            "discrepancy points must share positive dimension",
            reason="dimension_mismatch",
            field="points",
        )
    n = len(clean)
    first = (13.0 / 12.0) ** dimensions
    second = 0.0
    for point in clean:
        product_term = 1.0
        for value in point:
            product_term *= 1.0 + 0.5 * abs(value - 0.5) - 0.5 * (value - 0.5) ** 2
        second += product_term
    second *= 2.0 / n
    third = 0.0
    for left in clean:
        for right in clean:
            product_term = 1.0
            for a, b in zip(left, right):
                product_term *= (
                    1.0
                    + 0.5 * abs(a - 0.5)
                    + 0.5 * abs(b - 0.5)
                    - 0.5 * abs(a - b)
                )
            third += product_term
    third /= n * n
    squared = first - second + third
    return math.sqrt(max(0.0, squared))


def scale_unit_design(
    points: Sequence[Sequence[Real]],
    bounds: Sequence[tuple[Real, Real]],
) -> tuple[Vector, ...]:
    clean_bounds = []
    for axis, (lower, upper) in enumerate(bounds):
        lo = finite_scalar(f"bounds[{axis}].lower", lower)
        hi = finite_scalar(f"bounds[{axis}].upper", upper)
        if hi <= lo:
            raise MathInvariantError(
                "design bounds must satisfy lower < upper",
                reason="invalid_interval",
                field=f"bounds[{axis}]",
            )
        clean_bounds.append((lo, hi))
    output = []
    for row, point in enumerate(points):
        values = tuple(finite_scalar(f"points[{row}][{axis}]", value) for axis, value in enumerate(point))
        if len(values) != len(clean_bounds):
            raise MathInvariantError(
                "design point dimension must match bounds",
                reason="dimension_mismatch",
                field=f"points[{row}]",
            )
        if any(value < 0.0 or value > 1.0 for value in values):
            raise MathInvariantError(
                "design points must lie in the unit cube",
                reason="sample_out_of_bounds",
                field=f"points[{row}]",
            )
        output.append(tuple(
            lo + value * (hi - lo)
            for value, (lo, hi) in zip(values, clean_bounds)
        ))
    return tuple(output)
