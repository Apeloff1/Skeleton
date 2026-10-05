from __future__ import annotations
import hashlib
import pytest
from skeleton.ai.evaluation.human_evaluation import HumanEvaluationError,HumanEvaluationReport,HumanJudgment,RubricCriterion,build_human_report

def d(x): return hashlib.sha256(x.encode()).hexdigest()

def rubric():
    return (RubricCriterion("quality","Overall quality",1,5,1000000),)

def judgments():
    return (
        HumanJudgment("item","reviewer-a","quality",4,d("a")),
        HumanJudgment("item","reviewer-b","quality",5,d("b")),
    )

def test_human_evaluation_requires_independent_reviewers_and_binds_quality_vector():
    report=build_human_report(evaluation_id="eval",rubric=rubric(),judgments=judgments(),quality_vector_digest=d("quality"))
    assert report.reviewer_count==2
    assert 0<=report.aggregate_score_ppm<=1000000
    assert report.promotion_authority is False
    assert len(report.digest)==64

def test_single_reviewer_is_rejected():
    with pytest.raises(HumanEvaluationError,match="at least two"):
        build_human_report(
            evaluation_id="eval",rubric=rubric(),
            judgments=(HumanJudgment("item","only","quality",4,d("a")),),
            quality_vector_digest=d("q"),
        )

def test_score_outside_rubric_is_rejected():
    with pytest.raises(HumanEvaluationError,match="outside rubric"):
        build_human_report(
            evaluation_id="eval",rubric=rubric(),
            judgments=(HumanJudgment("item","a","quality",6,d("a")),HumanJudgment("item","b","quality",5,d("b"))),
            quality_vector_digest=d("q"),
        )

def test_report_cannot_claim_promotion_authority():
    report=build_human_report(evaluation_id="eval",rubric=rubric(),judgments=judgments(),quality_vector_digest=d("q"))
    with pytest.raises(HumanEvaluationError,match="cannot grant"):
        HumanEvaluationReport(report.evaluation_id,report.rubric,report.judgments,report.aggregate_score_ppm,report.reviewer_count,report.quality_vector_digest,True)
