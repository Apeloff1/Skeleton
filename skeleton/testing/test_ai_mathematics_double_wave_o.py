from __future__ import annotations

import math

import pytest

from skeleton.ai.mathematics import (
    BezierCurve,
    beta_cdf,
    beta_log_pdf,
    dirichlet_log_pdf,
    gamma_cdf,
    gamma_log_pdf,
    golden_section_minimize,
    mann_whitney_u,
    nelder_mead,
    one_way_anova,
    regularized_beta,
    welch_t_test,
)


def test_bezier_endpoints_derivative_and_split_consistency() -> None:
    curve = BezierCurve(((0.0, 0.0), (1.0, 2.0), (3.0, 2.0), (4.0, 0.0)))
    assert curve.evaluate(0.0) == pytest.approx((0.0, 0.0))
    assert curve.evaluate(1.0) == pytest.approx((4.0, 0.0))
    assert curve.derivative(0.0) == pytest.approx((3.0, 6.0))
    midpoint = curve.evaluate(0.5)
    left, right = curve.split(0.5)
    assert left.evaluate(1.0) == pytest.approx(midpoint, abs=1e-12)
    assert right.evaluate(0.0) == pytest.approx(midpoint, abs=1e-12)


def test_regularized_beta_and_distribution_references() -> None:
    assert regularized_beta(0.5, 2.0, 2.0) == pytest.approx(0.5, abs=1e-13)
    assert beta_cdf(0.5, 2.0, 2.0) == pytest.approx(0.5, abs=1e-13)
    assert math.exp(beta_log_pdf(0.5, 2.0, 2.0)) == pytest.approx(1.5)
    assert gamma_cdf(2.0, 1.0, scale=2.0) == pytest.approx(1.0 - math.exp(-1.0), abs=1e-13)
    assert math.exp(gamma_log_pdf(2.0, 1.0, scale=2.0)) == pytest.approx(math.exp(-1.0) / 2.0)
    assert dirichlet_log_pdf((0.2, 0.3, 0.5), (1.0, 1.0, 1.0)) == pytest.approx(math.log(2.0))


def test_welch_mann_whitney_and_anova_reference_cases() -> None:
    same = welch_t_test((1.0, 2.0, 3.0, 4.0), (1.0, 2.0, 3.0, 4.0))
    assert same.statistic == pytest.approx(0.0)
    assert same.two_sided_p_value == pytest.approx(1.0)

    shifted = welch_t_test((0.0, 0.2, 0.1, -0.1), (5.0, 5.2, 4.9, 5.1))
    assert shifted.two_sided_p_value < 1e-6

    mw = mann_whitney_u((1.0, 2.0, 3.0, 4.0), (10.0, 11.0, 12.0, 13.0))
    assert mw.u_left == pytest.approx(0.0)
    assert mw.two_sided_p_value < 0.05

    anova = one_way_anova(((1.0, 1.1, 0.9), (5.0, 5.1, 4.9), (9.0, 9.1, 8.9)))
    assert anova.f_statistic > 1000.0
    assert anova.p_value < 1e-6


def test_golden_section_and_nelder_mead_find_known_minima() -> None:
    golden = golden_section_minimize(lambda x: (x - 2.5) ** 2 + 3.0, -10.0, 10.0)
    assert golden.converged
    assert golden.minimizer == pytest.approx(2.5, abs=1e-8)
    assert golden.objective == pytest.approx(3.0, abs=1e-12)

    nelder = nelder_mead(
        lambda point: (point[0] - 3.0) ** 2 + 2.0 * (point[1] + 1.5) ** 2,
        (0.0, 0.0),
        initial_step=0.25,
    )
    assert nelder.converged
    assert nelder.solution == pytest.approx((3.0, -1.5), abs=1e-6)
    assert nelder.objective <= 1e-10
