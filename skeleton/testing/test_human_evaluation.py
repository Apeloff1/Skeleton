from __future__ import annotations

import pytest

from skeleton.ai.runtime.deferred.research_evaluation import HumanJudgment
from skeleton.ai.runtime.deferred.research_evaluation_assurance import (
    BlindedHumanJudgment,
    HumanRubric,
    ResearchEvaluationAssuranceError,
    aggregate_human_evaluation,
)


def rubric() -> HumanRubric:
    return HumanRubric("rubric-1", "v1", 2, 0.7)


def judgment(rater: str, score: float, *, blinded: bool = True):
    return BlindedHumanJudgment(
        HumanJudgment(rater, "case-1", "v1", score),
        blinded,
    )


def test_blinded_human_evaluation_binds_rubric_and_quality_vector() -> None:
    evidence = aggregate_human_evaluation(
        rubric(),
        (judgment("r1", 0.8), judgment("r2", 0.9)),
    )
    assert evidence.passed is True
    assert evidence.case_scores[0][0] == "case-1"\n    assert evidence.case_scores[0][1] == pytest.approx(0.85)
    assert evidence.quality_vector_eligible is True
    assert evidence.production_authority is False


def test_low_human_score_is_not_quality_vector_eligible() -> None:
    evidence = aggregate_human_evaluation(
        rubric(),
        (judgment("r1", 0.5), judgment("r2", 0.6)),
    )
    assert evidence.passed is False
    assert evidence.blockers == ("case-1:below-rubric",)
    assert evidence.quality_vector_eligible is False


def test_unblinded_or_rubric_drift_fails_closed() -> None:
    with pytest.raises(ResearchEvaluationAssuranceError, match="blinded"):
        judgment("r1", 0.8, blinded=False)

    with pytest.raises(ResearchEvaluationAssuranceError, match="version drift"):
        aggregate_human_evaluation(
            rubric(),
            (
                judgment("r1", 0.8),
                BlindedHumanJudgment(
                    HumanJudgment("r2", "case-1", "v2", 0.8),
                    True,
                ),
            ),
        )
