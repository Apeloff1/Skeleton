from __future__ import annotations

import pytest

from skeleton.ai.runtime.deferred.research_evaluation import Sample
from skeleton.ai.runtime.deferred.research_evaluation_assurance import (
    ResearchEvaluationAssuranceError,
    StatisticalAnalysisPlan,
    analyze_comparison,
)


def samples(group: str, values: tuple[float, ...]):
    return tuple(Sample(f"{group}-{i}", value, group) for i, value in enumerate(values))


def test_approved_statistical_plan_binds_sample_threshold_and_delta() -> None:
    plan = StatisticalAnalysisPlan(
        "analysis-1",
        "mean-difference",
        0.05,
        3,
        "accuracy",
    )
    result = analyze_comparison(
        plan,
        samples("base", (1.0, 2.0, 3.0)),
        samples("candidate", (2.0, 3.0, 4.0)),
    )
    assert result.sufficient_samples is True
    assert result.baseline_mean == pytest.approx(2.0)
    assert result.candidate_mean == pytest.approx(3.0)
    assert result.mean_delta == pytest.approx(1.0)
    assert len(result.plan_digest) == 64


def test_unapproved_method_and_bad_alpha_fail_closed() -> None:
    with pytest.raises(ResearchEvaluationAssuranceError, match="not approved"):
        StatisticalAnalysisPlan("a", "p-hack", 0.05, 3, "score")
    with pytest.raises(ResearchEvaluationAssuranceError, match="alpha"):
        StatisticalAnalysisPlan("a", "descriptive", 0.9, 3, "score")


def test_insufficient_samples_are_visible_not_silently_green() -> None:
    plan = StatisticalAnalysisPlan("a", "descriptive", 0.05, 5, "score")
    result = analyze_comparison(
        plan,
        samples("base", (1.0, 2.0)),
        samples("candidate", (1.0, 2.0)),
    )
    assert result.sufficient_samples is False
