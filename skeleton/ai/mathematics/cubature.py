"""Tensor-product Gauss-Legendre cubature over finite hyperrectangles."""
from __future__ import annotations

import itertools
from dataclasses import dataclass
from numbers import Real
from typing import Callable, Sequence

from .contracts import MathInvariantError, Vector, finite_scalar
from .numerics import compensated_sum
from .quadrature2 import gauss_legendre_rule


CubatureFunction = Callable[[Vector], Real]


@dataclass(frozen=True, slots=True)
class CubatureReport:
    estimate: float
    evaluations: int
    dimensions: int
    order: int
    panels_per_axis: int


def tensor_gauss_legendre_cubature(
    function: CubatureFunction,
    bounds: Sequence[tuple[Real, Real]],
    *,
    order: int = 4,
    panels_per_axis: int = 1,
) -> CubatureReport:
    if not bounds:
        raise MathInvariantError(
            "cubature requires at least one dimension",
            reason="empty_vector",
            field="bounds",
        )
    if len(bounds) > 8:
        raise MathInvariantError(
            "reference cubature is bounded to at most eight dimensions",
            reason="dimension_limit",
            field="bounds",
        )
    if isinstance(panels_per_axis, bool) or not isinstance(panels_per_axis, int) or panels_per_axis < 1:
        raise MathInvariantError(
            "panels_per_axis must be a positive integer",
            reason="invalid_panel_count",
            field="panels_per_axis",
        )
    clean_bounds: list[tuple[float, float]] = []
    for axis, (lower, upper) in enumerate(bounds):
        a = finite_scalar(f"bounds[{axis}].lower", lower)
        b = finite_scalar(f"bounds[{axis}].upper", upper)
        if b <= a:
            raise MathInvariantError(
                "cubature bounds must satisfy lower < upper",
                reason="invalid_interval",
                field=f"bounds[{axis}]",
            )
        clean_bounds.append((a, b))

    rule = gauss_legendre_rule(order)
    dimensions = len(clean_bounds)
    total = 0.0
    evaluations = 0

    panel_choices = itertools.product(range(panels_per_axis), repeat=dimensions)
    for panel_index in panel_choices:
        midpoints = []
        radii = []
        for axis, panel in enumerate(panel_index):
            lower, upper = clean_bounds[axis]
            width = (upper - lower) / panels_per_axis
            left = lower + panel * width
            right = left + width
            midpoints.append(0.5 * (left + right))
            radii.append(0.5 * width)

        for node_indices in itertools.product(range(order), repeat=dimensions):
            point = tuple(
                midpoints[axis] + radii[axis] * rule.nodes[node_indices[axis]]
                for axis in range(dimensions)
            )
            weight = 1.0
            for axis in range(dimensions):
                weight *= radii[axis] * rule.weights[node_indices[axis]]
            total += weight * finite_scalar("function_value", function(point))
            evaluations += 1

    return CubatureReport(
        estimate=finite_scalar("cubature_estimate", total),
        evaluations=evaluations,
        dimensions=dimensions,
        order=order,
        panels_per_axis=panels_per_axis,
    )


def integrate_rectangle_2d(
    function: Callable[[float, float], Real],
    x_bounds: tuple[Real, Real],
    y_bounds: tuple[Real, Real],
    *,
    order: int = 4,
) -> CubatureReport:
    return tensor_gauss_legendre_cubature(
        lambda point: function(point[0], point[1]),
        (x_bounds, y_bounds),
        order=order,
    )
