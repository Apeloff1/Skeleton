"""Deterministic asymmetric Durand-Kerner seeds avoid real-root oscillations."""
from __future__ import annotations

import pytest

from skeleton.ai.mathematics.polynomials import polynomial_roots


@pytest.mark.parametrize(
    ("coefficients", "expected"),
    [
        ((6, -7, 0, 1), (-3.0, 1.0, 2.0)),  # x^3 - 7x + 6
        ((6, -5, 1), (2.0, 3.0)),          # (x - 2)(x - 3)
        ((2, -3, 1), (1.0, 2.0)),          # (x - 1)(x - 2)
        ((4, 0, -5, 0, 1), (-2.0, -1.0, 1.0, 2.0)),
    ],
)
def test_real_root_families_converge_without_symmetric_oscillation(
    coefficients: tuple[int, ...], expected: tuple[float, ...],
) -> None:
    report = polynomial_roots(coefficients, tolerance=1e-12, max_iterations=100)
    assert report.converged
    assert report.iterations <= 100
    assert report.maximum_residual < 1e-9
    real_roots = sorted(root.real for root in report.roots)
    assert real_roots == pytest.approx(expected, abs=1e-8)
    assert all(abs(root.imag) < 1e-8 for root in report.roots)


def test_complex_roots_and_solver_seed_are_deterministic() -> None:
    a = polynomial_roots((-1, 0, 0, 1))
    b = polynomial_roots((-1, 0, 0, 1))
    assert a.converged and b.converged
    assert a.roots == b.roots
    assert a.maximum_residual < 1e-9
