from __future__ import annotations

import pytest

from skeleton.ai.mathematics import (
    benjamini_hochberg,
    benjamini_yekutieli,
    bonferroni,
    holm,
    huber_regression,
    theil_sen_regression,
)


def test_theil_sen_ignores_single_large_outlier() -> None:
    x = (0.0, 1.0, 2.0, 3.0, 4.0, 5.0)
    y = (1.0, 3.0, 5.0, 7.0, 9.0, 100.0)
    report = theil_sen_regression(x, y)
    assert report.slope == pytest.approx(2.0)
    assert report.intercept == pytest.approx(1.0)


def test_huber_regression_downweights_large_outlier() -> None:
    rows = tuple((float(index),) for index in range(8))
    targets = tuple(1.0 + 2.0 * index for index in range(7)) + (100.0,)
    report = huber_regression(rows, targets, tolerance=1e-11)
    assert report.converged
    assert report.coefficients[0] == pytest.approx(1.0, abs=0.2)
    assert report.coefficients[1] == pytest.approx(2.0, abs=0.1)
    assert report.weights[-1] < 0.1


def test_bonferroni_and_holm_adjustments_are_familywise_valid() -> None:
    raw = (0.001, 0.01, 0.04, 0.2)
    bon = bonferroni(raw, alpha=0.05)
    holm_report = holm(raw, alpha=0.05)
    assert bon.adjusted_p_values == pytest.approx((0.004, 0.04, 0.16, 0.8))
    assert holm_report.adjusted_p_values == pytest.approx((0.004, 0.03, 0.08, 0.2))
    assert holm_report.rejected == (True, True, False, False)


def test_bh_and_by_adjusted_p_values_are_monotone_in_sorted_order() -> None:
    raw = (0.01, 0.04, 0.03, 0.2, 0.001)
    bh = benjamini_hochberg(raw, alpha=0.05)
    by = benjamini_yekutieli(raw, alpha=0.05)
    order = sorted(range(len(raw)), key=lambda index: raw[index])
    bh_sorted = [bh.adjusted_p_values[index] for index in order]
    by_sorted = [by.adjusted_p_values[index] for index in order]
    assert all(left <= right for left, right in zip(bh_sorted, bh_sorted[1:]))
    assert all(left <= right for left, right in zip(by_sorted, by_sorted[1:]))
    assert all(by_value + 1e-15 >= bh_value for by_value, bh_value in zip(by.adjusted_p_values, bh.adjusted_p_values))
