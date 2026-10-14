"""Gauss-Legendre quadrature references generated from Legendre roots."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Callable

from .contracts import MathInvariantError, Vector, finite_scalar


ScalarFunction = Callable[[float], Real]


@dataclass(frozen=True, slots=True)
class GaussLegendreRule:
    nodes: Vector
    weights: Vector
    order: int


def gauss_legendre_rule(order: int) -> GaussLegendreRule:
    if isinstance(order, bool) or not isinstance(order, int) or not 2 <= order <= 64:
        raise MathInvariantError(
            "Gauss-Legendre order must be an integer in [2, 64]",
            reason="invalid_quadrature_order",
            field="order",
        )
    nodes = [0.0] * order
    weights = [0.0] * order
    half = (order + 1) // 2
    for i in range(half):
        root = math.cos(math.pi * (i + 0.75) / (order + 0.5))
        derivative = 0.0
        for _ in range(100):
            p0 = 1.0
            p1 = root
            if order == 1:
                pn = p1
                pnm1 = p0
            else:
                for degree in range(2, order + 1):
                    pn = ((2 * degree - 1) * root * p1 - (degree - 1) * p0) / degree
                    p0, p1 = p1, pn
                pn = p1
                pnm1 = p0
            derivative = order * (root * pn - pnm1) / (root * root - 1.0)
            correction = pn / derivative
            root -= correction
            if abs(correction) <= 2e-15:
                break
        else:
            raise MathInvariantError(
                "Legendre root iteration did not converge",
                reason="quadrature_non_convergence",
                field=f"root[{i}]",
            )
        weight = 2.0 / ((1.0 - root * root) * derivative * derivative)
        left = i
        right = order - 1 - i
        nodes[left] = -root
        nodes[right] = root
        weights[left] = weight
        weights[right] = weight
    return GaussLegendreRule(tuple(nodes), tuple(weights), order)


@dataclass(frozen=True, slots=True)
class GaussianQuadratureReport:
    estimate: float
    evaluations: int
    order: int
    panels: int


def gauss_legendre_integrate(
    function: ScalarFunction,
    lower: Real,
    upper: Real,
    *,
    order: int = 8,
    panels: int = 1,
) -> GaussianQuadratureReport:
    a = finite_scalar("lower", lower)
    b = finite_scalar("upper", upper)
    if isinstance(panels, bool) or not isinstance(panels, int) or panels < 1:
        raise MathInvariantError(
            "quadrature panels must be a positive integer",
            reason="invalid_panel_count",
            field="panels",
        )
    rule = gauss_legendre_rule(order)
    if a == b:
        return GaussianQuadratureReport(0.0, 0, order, panels)
    width = (b - a) / panels
    total = 0.0
    evaluations = 0
    for panel in range(panels):
        left = a + panel * width
        right = left + width
        midpoint = 0.5 * (left + right)
        radius = 0.5 * (right - left)
        panel_sum = 0.0
        for node, weight in zip(rule.nodes, rule.weights):
            value = finite_scalar("function_value", function(midpoint + radius * node))
            panel_sum += weight * value
            evaluations += 1
        total += radius * panel_sum
    return GaussianQuadratureReport(
        estimate=finite_scalar("quadrature_estimate", total),
        evaluations=evaluations,
        order=order,
        panels=panels,
    )
