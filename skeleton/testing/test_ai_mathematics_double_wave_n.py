from __future__ import annotations

import math

import pytest

from skeleton.ai.mathematics import (
    DenseTensor,
    assemble_linear_fem_1d,
    mode_product,
    oracle_approximating_shrinkage,
    rank_for_retained_energy,
    shrink_covariance,
    solve_poisson_fem_1d,
    tensor_contract,
    tensor_dot,
    tensor_outer,
    truncated_svd_approximation,
)


def test_tensor_contract_reproduces_matrix_product_and_full_dot() -> None:
    left = DenseTensor.matrix(((1.0, 2.0, 3.0), (4.0, 5.0, 6.0)))
    right = DenseTensor.matrix(((7.0, 8.0), (9.0, 10.0), (11.0, 12.0)))
    product = tensor_contract(left, right, left_axes=(1,), right_axes=(0,))
    assert product.shape == (2, 2)
    assert product.data == pytest.approx((58.0, 64.0, 139.0, 154.0))

    same = DenseTensor.matrix(((1.0, -2.0), (3.0, 4.0)))
    assert tensor_dot(same, same) == pytest.approx(30.0)


def test_tensor_outer_and_mode_product_shapes_and_values() -> None:
    left = DenseTensor.vector((1.0, 2.0))
    right = DenseTensor.vector((3.0, 4.0, 5.0))
    outer = tensor_outer(left, right)
    assert outer.shape == (2, 3)
    assert outer.data == pytest.approx((3.0, 4.0, 5.0, 6.0, 8.0, 10.0))

    tensor = DenseTensor((2, 2, 2), tuple(float(index) for index in range(8)))
    matrix = DenseTensor.matrix(((1.0, 0.0), (0.0, 2.0), (1.0, 1.0)))
    result = mode_product(tensor, matrix, 1)
    assert result.shape == (2, 3, 2)
    assert result.get(0, 0, 1) == pytest.approx(tensor.get(0, 0, 1))
    assert result.get(1, 1, 0) == pytest.approx(2.0 * tensor.get(1, 1, 0))


def test_linear_fem_assembly_and_poisson_solution() -> None:
    nodes = (0.0, 0.25, 0.5, 0.75, 1.0)
    assembly = assemble_linear_fem_1d(nodes)
    assert assembly.symmetry_linf == pytest.approx(0.0)
    assert sum(assembly.mass[0]) == pytest.approx(0.125)

    report = solve_poisson_fem_1d(nodes, lambda _x: 2.0)
    expected = tuple(x * (1.0 - x) for x in nodes)
    assert report.solution == pytest.approx(expected, abs=1e-12)
    assert report.algebraic_residual_linf <= 1e-12
    assert report.boundary_residual_linf == pytest.approx(0.0)


def test_covariance_shrinkage_improves_singular_spectrum() -> None:
    singular = ((1.0, 1.0), (1.0, 1.0))
    report = shrink_covariance(singular, 0.5, target="identity")
    assert report.minimum_eigenvalue > 0.0
    assert math.isfinite(report.spectral_condition)

    observations = (
        (1.0, 2.0, 3.0),
        (2.0, 4.0, 6.0),
        (3.0, 6.0, 9.0),
        (4.0, 8.0, 12.0),
    )
    oas = oracle_approximating_shrinkage(observations)
    assert 0.0 <= oas.intensity <= 1.0
    assert oas.minimum_eigenvalue > 0.0
    assert math.isfinite(oas.spectral_condition)


def test_truncated_svd_reports_retained_energy_and_residual() -> None:
    matrix = ((5.0, 0.0, 0.0), (0.0, 3.0, 0.0), (0.0, 0.0, 1.0))
    report = truncated_svd_approximation(matrix, 2)
    assert report.retained_energy_fraction == pytest.approx(34.0 / 35.0)
    assert report.residual_frobenius == pytest.approx(1.0)
    assert report.relative_residual_frobenius == pytest.approx(1.0 / math.sqrt(35.0))
    assert rank_for_retained_energy(matrix, 0.95) == 2
