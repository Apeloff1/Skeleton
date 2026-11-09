from __future__ import annotations

import math

import pytest

from skeleton.ai.mathematics import (
    MathInvariantError,
    RunningCovariance,
    RunningMoments,
    convex_hull,
    haar_transform,
    hadamard_transform,
    inverse_haar_transform,
    inverse_hadamard_transform,
    monotone_cubic_interpolator,
    point_in_polygon,
    polygon_area,
    polygon_centroid,
)


def test_running_moments_merge_matches_single_pass() -> None:
    values = (1.0, 2.0, 3.0, 4.0, 8.0)
    direct = RunningMoments()
    for value in values:
        direct = direct.update(value)

    left = RunningMoments()
    for value in values[:2]:
        left = left.update(value)
    right = RunningMoments()
    for value in values[2:]:
        right = right.update(value)
    merged = left.merge(right)

    assert merged.count == direct.count
    assert merged.mean == pytest.approx(direct.mean, abs=1e-15)
    assert merged.variance() == pytest.approx(direct.variance(), abs=1e-15)
    assert merged.minimum == 1.0
    assert merged.maximum == 8.0


def test_running_covariance_merge_and_correlation() -> None:
    pairs = ((1.0, 3.0), (2.0, 5.0), (3.0, 7.0), (4.0, 9.0))
    state = RunningCovariance()
    for x, y in pairs:
        state = state.update(x, y)
    assert state.correlation() == pytest.approx(1.0, abs=1e-15)
    assert state.covariance() == pytest.approx(10.0 / 3.0)

    a = RunningCovariance().update(*pairs[0]).update(*pairs[1])
    b = RunningCovariance().update(*pairs[2]).update(*pairs[3])
    merged = a.merge(b)
    assert merged.covariance() == pytest.approx(state.covariance(), abs=1e-15)


def test_haar_and_hadamard_round_trip_and_preserve_energy() -> None:
    values = (1.0, 2.0, -1.0, 4.0, 0.5, -2.0, 3.0, 1.5)
    haar = haar_transform(values)
    assert inverse_haar_transform(haar) == pytest.approx(values, abs=1e-12)
    hadamard = hadamard_transform(values)
    assert inverse_hadamard_transform(hadamard) == pytest.approx(values, abs=1e-12)
    energy = sum(value * value for value in values)
    assert sum(value * value for value in haar) == pytest.approx(energy, abs=1e-12)
    assert sum(value * value for value in hadamard) == pytest.approx(energy, abs=1e-12)


def test_wavelets_reject_non_power_of_two_length() -> None:
    with pytest.raises(MathInvariantError, match="power of two"):
        haar_transform((1.0, 2.0, 3.0))


def test_monotone_cubic_interpolator_preserves_monotone_range() -> None:
    interpolator = monotone_cubic_interpolator(
        (0.0, 1.0, 2.0, 4.0),
        (0.0, 1.0, 1.5, 3.0),
    )
    samples = tuple(interpolator.evaluate(index / 20.0 * 4.0) for index in range(21))
    assert all(left <= right + 1e-14 for left, right in zip(samples, samples[1:]))
    assert min(samples) >= 0.0
    assert max(samples) <= 3.0
    for x, y in zip(interpolator.knots, interpolator.values):
        assert interpolator.evaluate(x) == pytest.approx(y, abs=1e-12)


def test_convex_hull_polygon_area_centroid_and_containment() -> None:
    points = (
        (0.0, 0.0),
        (2.0, 0.0),
        (2.0, 2.0),
        (0.0, 2.0),
        (1.0, 1.0),
        (0.5, 0.5),
    )
    hull = convex_hull(points)
    assert len(hull) == 4
    assert polygon_area(hull) == pytest.approx(4.0)
    assert polygon_centroid(hull) == pytest.approx((1.0, 1.0))
    assert point_in_polygon((1.0, 1.0), hull)
    assert point_in_polygon((0.0, 1.0), hull)
    assert not point_in_polygon((0.0, 1.0), hull, include_boundary=False)
    assert not point_in_polygon((3.0, 1.0), hull)
