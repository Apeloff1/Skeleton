from __future__ import annotations

import pytest

from skeleton.contracts.canonical import EvidenceRef
from skeleton.intelligence.output_quality import (
    ArtifactType,
    ChangeImpact,
    IndependentQualityEvaluation,
    OutputDisposition,
    OutputKind,
    OutputQualityError,
    OutputQualityPolicy,
    ReasoningRegressionObservation,
    evaluate_answer_artifact_quality,
    required_artifact_gates,
)
from skeleton.intelligence.quality import QualityReport


def _ref(source: str, char: str) -> EvidenceRef:
    return EvidenceRef(
        source=source,
        digest=char * 64,
        category="quality_eval",
    )


def _report(
    *,
    score: float = 0.92,
    accepted: bool = True,
    metadata: dict | None = None,
) -> QualityReport:
    return QualityReport(
        accepted=accepted,
        reason="independent quality evaluation",
        score=score,
        thresholds={"minimum": 0.80},
        metadata={} if metadata is None else metadata,
    )


def _evaluation(
    kind: OutputKind,
    subject_id: str,
    char: str,
    *,
    score: float = 0.92,
    accepted: bool = True,
    independent: bool = True,
    metadata: dict | None = None,
) -> IndependentQualityEvaluation:
    artifact_kwargs = {}
    if kind is OutputKind.ARTIFACT:
        artifact_kwargs = {
            "artifact_type": ArtifactType.CODE,
            "change_impact": ChangeImpact.MEDIUM,
            "published_subject_digest": char * 64,
            "gate_ids": required_artifact_gates(
                ArtifactType.CODE,
                ChangeImpact.MEDIUM,
            ),
        }
    return IndependentQualityEvaluation(
        kind=kind,
        subject_id=subject_id,
        subject_digest=char * 64,
        evaluator_id=f"eval:{subject_id}",
        evaluator_digest="e" * 64,
        report=_report(score=score, accepted=accepted, metadata=metadata),
        evidence_refs=(_ref(f"quality://{subject_id}", "f"),),
        independent=independent,
        **artifact_kwargs,
    )


def _regression(
    *,
    suite_id: str = "reasoning-core",
    baseline_score: float = 0.90,
    candidate_score: float = 0.89,
    max_allowed_drop: float = 0.02,
    independent: bool = True,
) -> ReasoningRegressionObservation:
    return ReasoningRegressionObservation(
        suite_id=suite_id,
        baseline_digest="1" * 64,
        candidate_digest="2" * 64,
        baseline_score=baseline_score,
        candidate_score=candidate_score,
        max_allowed_drop=max_allowed_drop,
        evaluator_id=f"regression:{suite_id}",
        evaluator_digest="3" * 64,
        evidence_refs=(_ref(f"regression://{suite_id}", "4"),),
        independent=independent,
    )


def test_accepts_independent_answer_artifact_and_reasoning_quality() -> None:
    answer = _evaluation(OutputKind.ANSWER, "answer-1", "a")
    artifact = _evaluation(OutputKind.ARTIFACT, "artifact-1", "b")
    regression = _regression()

    decision = evaluate_answer_artifact_quality(
        answer=answer,
        artifacts=(artifact,),
        expected_artifact_digests=(artifact.subject_digest,),
        reasoning_regressions=(regression,),
    )

    assert decision.accepted is True
    assert decision.reasons == ()
    assert len(decision.decision_digest) == 64
    evidence = decision.accepted_evidence_ref()
    assert evidence.category == "answer_artifact_quality"
    assert evidence.digest == decision.decision_digest


def test_answer_evaluator_must_be_independent() -> None:
    decision = evaluate_answer_artifact_quality(
        answer=_evaluation(
            OutputKind.ANSWER,
            "answer-1",
            "a",
            independent=False,
        ),
        reasoning_regressions=(_regression(),),
    )

    assert decision.accepted is False
    assert "answer-evaluator-not-independent" in decision.reasons


def test_model_self_confidence_cannot_substitute_for_verification() -> None:
    answer = _evaluation(
        OutputKind.ANSWER,
        "answer-1",
        "a",
        score=0.99,
        metadata={
            "quality_source": "model_self_report",
            "self_confidence": 0.999,
        },
    )

    decision = evaluate_answer_artifact_quality(
        answer=answer,
        reasoning_regressions=(_regression(),),
    )

    assert decision.accepted is False
    assert "answer-self-confidence-is-not-verification" in decision.reasons


def test_answer_quality_threshold_is_fail_closed() -> None:
    decision = evaluate_answer_artifact_quality(
        answer=_evaluation(
            OutputKind.ANSWER,
            "answer-1",
            "a",
            score=0.79,
        ),
        reasoning_regressions=(_regression(),),
    )

    assert decision.accepted is False
    assert "answer-quality-below-threshold" in decision.reasons


def test_declared_artifact_requires_exact_quality_coverage() -> None:
    missing = "b" * 64
    decision = evaluate_answer_artifact_quality(
        answer=_evaluation(OutputKind.ANSWER, "answer-1", "a"),
        expected_artifact_digests=(missing,),
        reasoning_regressions=(_regression(),),
    )

    assert decision.accepted is False
    assert any(
        reason.startswith("artifact-quality-missing:")
        for reason in decision.reasons
    )


def test_undeclared_artifact_quality_is_not_silently_counted() -> None:
    artifact = _evaluation(OutputKind.ARTIFACT, "artifact-1", "b")
    decision = evaluate_answer_artifact_quality(
        answer=_evaluation(OutputKind.ANSWER, "answer-1", "a"),
        artifacts=(artifact,),
        expected_artifact_digests=(),
        reasoning_regressions=(_regression(),),
    )

    assert decision.accepted is False
    assert any(
        reason.startswith("artifact-quality-unexpected:")
        for reason in decision.reasons
    )


def test_artifact_quality_is_independent_and_thresholded() -> None:
    artifact = _evaluation(
        OutputKind.ARTIFACT,
        "artifact-1",
        "b",
        score=0.70,
        independent=False,
    )
    decision = evaluate_answer_artifact_quality(
        answer=_evaluation(OutputKind.ANSWER, "answer-1", "a"),
        artifacts=(artifact,),
        expected_artifact_digests=(artifact.subject_digest,),
        reasoning_regressions=(_regression(),),
    )

    assert decision.accepted is False
    assert "artifact-evaluator-not-independent:artifact-1" in decision.reasons
    assert "artifact-quality-below-threshold:artifact-1" in decision.reasons


def test_reasoning_regression_evidence_is_required() -> None:
    decision = evaluate_answer_artifact_quality(
        answer=_evaluation(OutputKind.ANSWER, "answer-1", "a"),
    )

    assert decision.accepted is False
    assert "reasoning-regression-evidence-missing" in decision.reasons


def test_reasoning_regression_must_not_exceed_bound() -> None:
    decision = evaluate_answer_artifact_quality(
        answer=_evaluation(OutputKind.ANSWER, "answer-1", "a"),
        reasoning_regressions=(
            _regression(
                baseline_score=0.90,
                candidate_score=0.80,
                max_allowed_drop=0.02,
            ),
        ),
    )

    assert decision.accepted is False
    assert "reasoning-regression-exceeded:reasoning-core" in decision.reasons


def test_reasoning_regression_must_be_independent() -> None:
    decision = evaluate_answer_artifact_quality(
        answer=_evaluation(OutputKind.ANSWER, "answer-1", "a"),
        reasoning_regressions=(_regression(independent=False),),
    )

    assert decision.accepted is False
    assert "reasoning-regression-not-independent:reasoning-core" in decision.reasons


def test_artifact_and_regression_order_do_not_change_decision_identity() -> None:
    answer = _evaluation(OutputKind.ANSWER, "answer-1", "a")
    first = _evaluation(OutputKind.ARTIFACT, "artifact-1", "b")
    second = _evaluation(OutputKind.ARTIFACT, "artifact-2", "c")
    r1 = _regression(suite_id="suite-a")
    r2 = ReasoningRegressionObservation(
        suite_id="suite-b",
        baseline_digest="5" * 64,
        candidate_digest="6" * 64,
        baseline_score=0.90,
        candidate_score=0.90,
        max_allowed_drop=0.01,
        evaluator_id="regression:suite-b",
        evaluator_digest="7" * 64,
        evidence_refs=(_ref("regression://suite-b", "8"),),
    )

    left = evaluate_answer_artifact_quality(
        answer=answer,
        artifacts=(first, second),
        expected_artifact_digests=(first.subject_digest, second.subject_digest),
        reasoning_regressions=(r1, r2),
    )
    right = evaluate_answer_artifact_quality(
        answer=answer,
        artifacts=(second, first),
        expected_artifact_digests=(second.subject_digest, first.subject_digest),
        reasoning_regressions=(r2, r1),
    )

    assert left.accepted is True
    assert right.accepted is True
    assert left.decision_digest == right.decision_digest


def test_quality_metadata_key_order_is_canonical() -> None:
    left = _evaluation(
        OutputKind.ANSWER,
        "answer-1",
        "a",
        metadata={"rubric": "v1", "dataset": "gold"},
    )
    right = _evaluation(
        OutputKind.ANSWER,
        "answer-1",
        "a",
        metadata={"dataset": "gold", "rubric": "v1"},
    )

    assert left.digest == right.digest


def test_rejected_decision_cannot_become_promotion_evidence() -> None:
    decision = evaluate_answer_artifact_quality(
        answer=_evaluation(
            OutputKind.ANSWER,
            "answer-1",
            "a",
            score=0.20,
        ),
        reasoning_regressions=(_regression(),),
    )

    with pytest.raises(OutputQualityError, match="cannot become"):
        decision.accepted_evidence_ref()


def test_duplicate_artifact_subject_is_rejected() -> None:
    first = _evaluation(OutputKind.ARTIFACT, "artifact-1", "b")
    duplicate = _evaluation(OutputKind.ARTIFACT, "artifact-2", "b")

    with pytest.raises(OutputQualityError, match="duplicate artifact"):
        evaluate_answer_artifact_quality(
            answer=_evaluation(OutputKind.ANSWER, "answer-1", "a"),
            artifacts=(first, duplicate),
            expected_artifact_digests=(first.subject_digest,),
            reasoning_regressions=(_regression(),),
        )


def test_malformed_scores_fail_at_contract_boundary() -> None:
    with pytest.raises(OutputQualityError, match="report.score"):
        _evaluation(
            OutputKind.ANSWER,
            "answer-1",
            "a",
            score=float("nan"),
        )

    with pytest.raises(OutputQualityError, match="candidate_score"):
        _regression(candidate_score=1.1)


def test_policy_can_raise_quality_floor_without_changing_evidence() -> None:
    answer = _evaluation(OutputKind.ANSWER, "answer-1", "a", score=0.90)
    regression = _regression()

    passing = evaluate_answer_artifact_quality(
        answer=answer,
        reasoning_regressions=(regression,),
        policy=OutputQualityPolicy(min_answer_score=0.90),
    )
    failing = evaluate_answer_artifact_quality(
        answer=answer,
        reasoning_regressions=(regression,),
        policy=OutputQualityPolicy(min_answer_score=0.95),
    )

    assert passing.accepted is True
    assert failing.accepted is False
    assert passing.answer_evaluation_digest == failing.answer_evaluation_digest
    assert passing.policy_digest != failing.policy_digest


def test_answer_outcomes_distinguish_qualified_abstained_and_blocked() -> None:
    answer = _evaluation(OutputKind.ANSWER, "answer-1", "a")
    regression = _regression()

    qualified = evaluate_answer_artifact_quality(
        answer=answer,
        reasoning_regressions=(regression,),
    )
    abstained = evaluate_answer_artifact_quality(
        answer=answer,
        reasoning_regressions=(regression,),
        answer_disposition=OutputDisposition.ABSTAINED,
    )
    blocked = evaluate_answer_artifact_quality(
        answer=answer,
        reasoning_regressions=(regression,),
        answer_disposition=OutputDisposition.BLOCKED,
    )

    assert qualified.disposition is OutputDisposition.QUALIFIED
    assert qualified.accepted is True
    assert qualified.payload()["publication_allowed"] is True
    assert abstained.disposition is OutputDisposition.ABSTAINED
    assert abstained.accepted is False
    assert "answer-abstained" in abstained.reasons
    assert abstained.payload()["publication_allowed"] is False
    assert blocked.disposition is OutputDisposition.BLOCKED
    assert blocked.accepted is False
    assert "answer-explicitly-blocked" in blocked.reasons


def test_artifact_requires_type_and_change_impact_gate_profile() -> None:
    answer = _evaluation(OutputKind.ANSWER, "answer-1", "a")
    regression = _regression()
    artifact = IndependentQualityEvaluation(
        kind=OutputKind.ARTIFACT,
        subject_id="artifact-critical",
        subject_digest="b" * 64,
        evaluator_id="eval:artifact-critical",
        evaluator_digest="e" * 64,
        report=_report(),
        evidence_refs=(_ref("quality://artifact-critical", "f"),),
        artifact_type=ArtifactType.CONFIGURATION,
        change_impact=ChangeImpact.CRITICAL,
        published_subject_digest="b" * 64,
        gate_ids=("schema", "rollback"),
    )

    decision = evaluate_answer_artifact_quality(
        answer=answer,
        artifacts=(artifact,),
        expected_artifact_digests=(artifact.subject_digest,),
        reasoning_regressions=(regression,),
    )

    assert decision.accepted is False
    reason = next(
        item
        for item in decision.reasons
        if item.startswith("artifact-required-gates-missing:")
    )
    assert "security" in reason
    assert "independent-release" in reason


def test_artifact_under_test_must_equal_published_artifact() -> None:
    answer = _evaluation(OutputKind.ANSWER, "answer-1", "a")
    regression = _regression()
    artifact = IndependentQualityEvaluation(
        kind=OutputKind.ARTIFACT,
        subject_id="artifact-versioned",
        subject_digest="b" * 64,
        evaluator_id="eval:artifact-versioned",
        evaluator_digest="e" * 64,
        report=_report(),
        evidence_refs=(_ref("quality://artifact-versioned", "f"),),
        artifact_type=ArtifactType.CODE,
        change_impact=ChangeImpact.HIGH,
        published_subject_digest="c" * 64,
        gate_ids=required_artifact_gates(
            ArtifactType.CODE,
            ChangeImpact.HIGH,
        ),
    )

    decision = evaluate_answer_artifact_quality(
        answer=answer,
        artifacts=(artifact,),
        expected_artifact_digests=(artifact.subject_digest,),
        reasoning_regressions=(regression,),
    )

    assert decision.accepted is False
    assert (
        "artifact-published-digest-mismatch:artifact-versioned"
        in decision.reasons
    )


def test_artifact_gate_registry_varies_by_type_and_impact() -> None:
    code_low = set(
        required_artifact_gates(ArtifactType.CODE, ChangeImpact.LOW)
    )
    code_critical = set(
        required_artifact_gates(
            ArtifactType.CODE,
            ChangeImpact.CRITICAL,
        )
    )
    document_low = set(
        required_artifact_gates(
            ArtifactType.DOCUMENT,
            ChangeImpact.LOW,
        )
    )

    assert code_low == {"static-analysis", "tests"}
    assert document_low == {"factuality", "link-integrity"}
    assert code_low < code_critical
    assert {"security", "rollback", "independent-release"} <= code_critical
