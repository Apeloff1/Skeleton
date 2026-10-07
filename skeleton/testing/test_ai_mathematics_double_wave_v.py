from __future__ import annotations

import pytest

from skeleton.ai.mathematics import (
    BSplineSurface,
    BezierSurface,
    DenseTensor,
    clamped_uniform_knots,
    hosvd,
    tucker_reconstruct,
    unfold_tensor,
)


def test_bezier_surface_recovers_bilinear_plane_and_partials() -> None:
    surface = BezierSurface(
        (
            ((0.0, 0.0, 0.0), (0.0, 1.0, 2.0)),
            ((1.0, 0.0, 3.0), (1.0, 1.0, 5.0)),
        )
    )
    value = surface.evaluate(0.25, 0.75)
    assert value == pytest.approx((0.25, 0.75, 2.25), abs=1e-12)
    assert surface.partial_u(0.4, 0.6) == pytest.approx((1.0, 0.0, 3.0), abs=1e-12)
    assert surface.partial_v(0.4, 0.6) == pytest.approx((0.0, 1.0, 2.0), abs=1e-12)


def test_bspline_surface_hits_clamped_corners() -> None:
    control = (
        ((0.0, 0.0), (0.0, 1.0), (0.0, 2.0)),
        ((1.0, 0.0), (1.0, 1.0), (1.0, 2.0)),
        ((2.0, 0.0), (2.0, 1.0), (2.0, 2.0)),
    )
    knots = clamped_uniform_knots(3, 2)
    surface = BSplineSurface(control, knots, knots, 2, 2)
    assert surface.evaluate(0.0, 0.0) == pytest.approx((0.0, 0.0))
    assert surface.evaluate(1.0, 1.0) == pytest.approx((2.0, 2.0))


def test_hosvd_rank_one_tensor_reconstructs_exactly() -> None:
    a = (1.0, 2.0)
    b = (1.0, -1.0, 0.5)
    c = (2.0, 3.0)
    data = tuple(x * y * z for x in a for y in b for z in c)
    tensor = DenseTensor((2, 3, 2), data)
    report = hosvd(tensor, ranks=(1, 1, 1))
    assert report.core.shape == (1, 1, 1)
    assert report.ranks == (1, 1, 1)
    assert report.residual_frobenius <= 1e-10
    assert report.relative_residual_frobenius <= 1e-12
    rebuilt = tucker_reconstruct(report.core, report.factors)
    assert rebuilt.data == pytest.approx(tensor.data, abs=1e-10)


def test_tensor_unfolding_has_expected_shape_and_order() -> None:
    tensor = DenseTensor((2, 2, 2), tuple(float(index) for index in range(8)))
    mode_one = unfold_tensor(tensor, 1)
    assert len(mode_one) == 2
    assert len(mode_one[0]) == 4
    assert mode_one[0] == pytest.approx((0.0, 1.0, 4.0, 5.0))
    assert mode_one[1] == pytest.approx((2.0, 3.0, 6.0, 7.0))
