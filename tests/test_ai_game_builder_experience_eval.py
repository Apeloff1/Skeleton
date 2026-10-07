from __future__ import annotations

import pytest

from skeleton.ai.game_builder.contracts import EvaluatorProvenance, canonical_digest
from skeleton.ai.game_builder.experience_eval import (
    EXPERIENCE_METRICS,
    ExperienceDefect,
    ExperienceEvaluationError,
    ExperienceObservation,
    build_experience_report,
    evaluate_experience_promotion,
)


def _authority(
    evaluator_id: str,
    evidence_digest: str,
    *,
    method_id: str = "playtest-v1",
) -> EvaluatorProvenance:
    return EvaluatorProvenance(
        evaluator_id=evaluator_id,
        operation_id=f"operation:{evaluator_id}",
        execution_id=f"execution:{evaluator_id}",
        execution_identity_digest=canonical_digest({"execution": evaluator_id}),
        finalization_intent_digest=canonical_digest({"finalization": evaluator_id}),
        authority_kind="deterministic_control",
        authority_identity_digest=canonical_digest({"authority": evaluator_id}),
        method_id=method_id,
        source_revision=canonical_digest({"source": evaluator_id})[:40],
        output_evidence_refs=(evidence_digest,),
    )


def _metrics(*, engagement: float, friction: float, learning: float, value: float) -> dict[str, float]:
    return {
        "engagement_proxy": engagement,
        "friction_detection": friction,
        "learning_curve": learning,
        "player_value_density": value,
    }


def _observation(
    observation_id: str,
    evaluator_id: str,
    *,
    artifact: str = "a" * 64,
    revision: str = "rev-1",
    metrics: dict[str, float] | None = None,
) -> ExperienceObservation:
    return ExperienceObservation.create(
        observation_id=observation_id,
        artifact_digest=artifact,
        project_revision=revision,
        evaluator_id=evaluator_id,
        method_id="playtest-v1",
        atomic_target_id="scene:opening:beat-3",
        parent_context=("scene:opening", "chapter:1", "project:demo"),
        observed_facts=("player retried the interaction twice",),
        interpretations=("instruction affordance may be unclear",),
        metrics=metrics
        or _metrics(
            engagement=0.70,
            friction=0.75,
            learning=0.80,
            value=0.72,
        ),
        evaluator_provenance=_authority(evaluator_id, "e" * 64),
        evidence_digest="e" * 64,
    )


def test_observation_requires_exact_metric_contract_and_parent_traceability() -> None:
    observation = _observation("OBS-1", "eval-a")
    assert tuple(observation.metric_map) == EXPERIENCE_METRICS
    assert observation.parent_context[-1] == "project:demo"

    with pytest.raises(ValueError, match="metric contract drift"):
        ExperienceObservation.create(
            observation_id="OBS-bad",
            artifact_digest="a" * 64,
            project_revision="rev-1",
            evaluator_id="eval-a",
            method_id="playtest-v1",
            atomic_target_id="beat:1",
            parent_context=("scene:1",),
            observed_facts=("fact",),
            interpretations=(),
            metrics={"engagement_proxy": 0.5},
            evaluator_provenance=_authority("eval-a", "e" * 64),
            evidence_digest="e" * 64,
        )

    with pytest.raises(ValueError, match="parent context"):
        ExperienceObservation.create(
            observation_id="OBS-bad-parent",
            artifact_digest="a" * 64,
            project_revision="rev-1",
            evaluator_id="eval-a",
            method_id="playtest-v1",
            atomic_target_id="beat:1",
            parent_context=(),
            observed_facts=("fact",),
            interpretations=(),
            metrics=_metrics(engagement=0.5, friction=0.5, learning=0.5, value=0.5),
            evaluator_provenance=_authority("eval-a", "e" * 64),
            evidence_digest="e" * 64,
        )


def test_observation_rejects_evidence_or_identity_detached_from_provenance() -> None:
    with pytest.raises(
        ExperienceEvaluationError,
        match="evidence must be referenced",
    ):
        ExperienceObservation.create(
            observation_id="OBS-unbound",
            artifact_digest="a" * 64,
            project_revision="rev-1",
            evaluator_id="eval-a",
            method_id="playtest-v1",
            atomic_target_id="beat:1",
            parent_context=("scene:1",),
            observed_facts=("fact",),
            interpretations=(),
            metrics=_metrics(
                engagement=0.5,
                friction=0.5,
                learning=0.5,
                value=0.5,
            ),
            evaluator_provenance=_authority("eval-a", "x" * 64),
            evidence_digest="e" * 64,
        )

    with pytest.raises(
        ExperienceEvaluationError,
        match="identity does not match provenance",
    ):
        ExperienceObservation.create(
            observation_id="OBS-wrong-identity",
            artifact_digest="a" * 64,
            project_revision="rev-1",
            evaluator_id="eval-a",
            method_id="playtest-v1",
            atomic_target_id="beat:1",
            parent_context=("scene:1",),
            observed_facts=("fact",),
            interpretations=(),
            metrics=_metrics(
                engagement=0.5,
                friction=0.5,
                learning=0.5,
                value=0.5,
            ),
            evaluator_provenance=_authority("eval-b", "e" * 64),
            evidence_digest="e" * 64,
        )


def test_critical_defect_resolution_requires_independent_attributed_authority() -> None:
    evidence = "f" * 64
    resolution = "r" * 64
    with pytest.raises(
        ExperienceEvaluationError,
        match="requires independent authority",
    ):
        ExperienceDefect(
            defect_id="DEF-critical",
            artifact_digest="b" * 64,
            severity=8,
            summary="Critical progression failure.",
            evidence_digest=evidence,
            affected_context=("scene:tutorial",),
            evaluator_provenance=_authority(
                "same-reviewer",
                evidence,
                method_id="critical-defect-review",
            ),
            resolved_by_digest=resolution,
            resolution_authority=_authority(
                "same-reviewer",
                resolution,
                method_id="defect-resolution",
            ),
        )


def test_report_is_order_stable_and_requires_independent_evaluator_diversity() -> None:
    left = _observation(
        "OBS-1",
        "eval-a",
        metrics=_metrics(engagement=0.60, friction=0.70, learning=0.80, value=0.65),
    )
    right = _observation(
        "OBS-2",
        "eval-b",
        metrics=_metrics(engagement=0.80, friction=0.90, learning=0.70, value=0.85),
    )

    first = build_experience_report((left, right))
    second = build_experience_report((right, left))

    assert first.report_digest == second.report_digest
    assert first.metric_map == {
        "engagement_proxy": 0.70,
        "friction_detection": 0.80,
        "learning_curve": 0.75,
        "player_value_density": 0.75,
    }
    assert first.evaluator_ids == ("eval-a", "eval-b")

    with pytest.raises(ExperienceEvaluationError, match="report digest mismatch"):
        type(first)(
            artifact_digest=first.artifact_digest,
            project_revision=first.project_revision,
            evaluator_ids=first.evaluator_ids,
            observation_digests=first.observation_digests,
            defect_digests=first.defect_digests,
            aggregate_metrics=tuple(
                (name, value + 0.01 if name == "engagement_proxy" else value)
                for name, value in first.aggregate_metrics
            ),
            unresolved_critical_defects=first.unresolved_critical_defects,
            report_digest=first.report_digest,
        )

    with pytest.raises(ExperienceEvaluationError, match="diversity"):
        build_experience_report((left,))


def test_report_rejects_mixed_artifact_or_revision_identity() -> None:
    left = _observation("OBS-1", "eval-a")
    wrong = _observation("OBS-2", "eval-b", artifact="b" * 64)

    with pytest.raises(ExperienceEvaluationError, match="artifact/revision"):
        build_experience_report((left, wrong))


def test_promotion_requires_pareto_safe_gain() -> None:
    baseline = build_experience_report(
        (
            _observation(
                "BASE-1",
                "eval-a",
                metrics=_metrics(engagement=0.60, friction=0.60, learning=0.60, value=0.60),
            ),
            _observation(
                "BASE-2",
                "eval-b",
                metrics=_metrics(engagement=0.60, friction=0.60, learning=0.60, value=0.60),
            ),
        )
    )
    candidate = build_experience_report(
        (
            _observation(
                "CAND-1",
                "eval-a",
                artifact="b" * 64,
                revision="rev-2",
                metrics=_metrics(engagement=0.75, friction=0.65, learning=0.70, value=0.80),
            ),
            _observation(
                "CAND-2",
                "eval-b",
                artifact="b" * 64,
                revision="rev-2",
                metrics=_metrics(engagement=0.75, friction=0.65, learning=0.70, value=0.80),
            ),
        )
    )

    decision = evaluate_experience_promotion(baseline, candidate)
    assert decision.eligible is True
    assert decision.pareto_safe is True
    assert decision.regressed_metrics == ()
    assert set(decision.improved_metrics) == set(EXPERIENCE_METRICS)

    with pytest.raises(
        ExperienceEvaluationError,
        match="promotion decision digest mismatch",
    ):
        type(decision)(
            baseline_report_digest=decision.baseline_report_digest,
            candidate_report_digest=decision.candidate_report_digest,
            eligible=False,
            pareto_safe=decision.pareto_safe,
            improved_metrics=decision.improved_metrics,
            regressed_metrics=decision.regressed_metrics,
            blockers=decision.blockers,
            decision_digest=decision.decision_digest,
        )


def test_promotion_blocks_metric_regression_and_unresolved_critical_defect() -> None:
    baseline = build_experience_report(
        (
            _observation(
                "BASE-1",
                "eval-a",
                metrics=_metrics(engagement=0.70, friction=0.70, learning=0.70, value=0.70),
            ),
            _observation(
                "BASE-2",
                "eval-b",
                metrics=_metrics(engagement=0.70, friction=0.70, learning=0.70, value=0.70),
            ),
        )
    )
    rows = (
        _observation(
            "CAND-1",
            "eval-a",
            artifact="b" * 64,
            revision="rev-2",
            metrics=_metrics(engagement=0.90, friction=0.60, learning=0.80, value=0.80),
        ),
        _observation(
            "CAND-2",
            "eval-b",
            artifact="b" * 64,
            revision="rev-2",
            metrics=_metrics(engagement=0.90, friction=0.60, learning=0.80, value=0.80),
        ),
    )
    defect = ExperienceDefect(
        defect_id="DEF-1",
        artifact_digest="b" * 64,
        severity=8,
        summary="Critical onboarding trap blocks progress.",
        evidence_digest="f" * 64,
        affected_context=("scene:tutorial", "project:demo"),
        evaluator_provenance=_authority(
            "critical-defect-evaluator",
            "f" * 64,
            method_id="critical-defect-review",
        ),
    )
    candidate = build_experience_report(rows, defects=(defect,))

    decision = evaluate_experience_promotion(baseline, candidate)
    assert decision.eligible is False
    assert decision.pareto_safe is False
    assert decision.regressed_metrics == ("friction_detection",)
    assert "experience metric regression" in decision.blockers
    assert "candidate has unresolved critical experience defects" in decision.blockers


def test_creative_rivals_cannot_self_supply_independent_experience_evidence() -> None:
    with pytest.raises(ValueError, match="independent from both rivals"):
        _observation("OBS-RIVAL", "rival_a")
