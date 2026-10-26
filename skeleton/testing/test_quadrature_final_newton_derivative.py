"""Gauss-Legendre weights must correspond to converged Newton roots."""
from __future__ import annotations

import math

import pytest

from skeleton.ai.mathematics.quadrature2 import (
    gauss_legendre_integrate,
    gauss_legendre_rule,
)


@pytest.mark.parametrize("order", [3, 4, 5, 6, 8, 12, 16])
def test_quadrature_weights_integrate_constant_to_machine_precision(order: int) -> None:
    rule = gauss_legendre_rule(order)
    assert len(rule.nodes) == len(rule.weights) == order
    assert all(math.isfinite(w) and w > 0 for w in rule.weights)
    assert abs(math.fsum(rule.weights) - 2.0) < 2e-15


@pytest.mark.parametrize("order", [4, 5, 8, 12])
def test_quadrature_rule_integrates_x_squared_exactly(order: int) -> None:
    rule = gauss_legendre_rule(order)
    moment = math.fsum(w * x * x for x, w in zip(rule.nodes, rule.weights))
    assert abs(moment - 2.0 / 3.0) < 2e-15


@pytest.mark.parametrize("order", [4, 5, 8, 12])
def test_quadrature_nodes_and_weights_preserve_reflection_symmetry(order: int) -> None:
    rule = gauss_legendre_rule(order)
    for i in range(order):
        j = order - i - 1
        assert rule.nodes[i] == -rule.nodes[j]
        assert rule.weights[i] == rule.weights[j]


def test_integrator_uses_corrected_weights_without_changing_evaluation_count() -> None:
    report = gauss_legendre_integrate(lambda x: 1.0, -1.0, 1.0, order=4, panels=3)
    assert abs(report.estimate - 2.0) < 2e-15
    assert report.evaluations == 12 and report.panels == 3
