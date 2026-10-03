from __future__ import annotations

from types import SimpleNamespace

import pytest

from skeleton.eval.firewall import (
    EvaluationFirewall,
    EvaluationSet,
    EvaluatorIdentity,
)
from skeleton.learning.mirror_room.promotion import MirrorPromotionEvidence

from skeleton.ai.runtime.inference.training_allocation import (
    MethodValidationObservation,
    TrainingAllocationError,
    TrainingAllocationPolicy,
    allocate_training_methods,
    observe_mirror_validation,
)
from skeleton.ai.runtime.inference.training_methods import TrainingMethod
from skeleton.ai.runtime.product.qualification import (
    LearningQualificationError,
    MirrorModelBinding,
    qualify_learning_candidate,
)


def _sha(seed: str) -> str:
    import hashlib

    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _observation(
    method: TrainingMethod,
    *,
    gain: float,
    compute: float,
    index: int,
    evaluation_class: str = "mirror_validation",
) -> MethodValidationObservation:
    return MethodValidationObservation(
        method=method,
        evaluation_class=evaluation_class,
        validation_gain=gain,
        compute_units=compute,
        evaluation_digest=_sha(f"eval-{method.value}-{index}"),
        plan_digest=_sha(f"plan-{index}"),
        sample_count=4,
    )


def test_adaptive_allocation_favors_validation_gain_per_compute() -> None:
    allocation = allocate_training_methods(
        (
            _observation(
                TrainingMethod.SUPERVISED_INSTRUCTION,
                gain=0.40,
                compute=1.0,
                index=1,
            ),
            _observation(
                TrainingMethod.CONTRASTIVE,
                gain=0.20,
                compute=2.0,
                index=2,
            ),
            _observation(
                TrainingMethod.ADVERSARIAL_ROBUSTNESS,
                gain=-0.05,
                compute=1.0,
                index=3,
            ),
        ),
        available_methods=(
            TrainingMethod.SUPERVISED_INSTRUCTION,
            TrainingMethod.CAUSAL_LANGUAGE_MODELING,
            TrainingMethod.SELF_SUPERVISED_SPAN,
            TrainingMethod.CONTRASTIVE,
            TrainingMethod.ADVERSARIAL_ROBUSTNESS,
        ),
        policy=TrainingAllocationPolicy(
            max_repeat_per_method=4,
            max_total_repeats=10,
            exploration_repeat=1,
        ),
    )

    by_method = {
        item.method: item.repeat
        for item in allocation.method_weights
    }
    assert (
        by_method[TrainingMethod.SUPERVISED_INSTRUCTION]
        > by_method[TrainingMethod.CONTRASTIVE]
    )
    assert TrainingMethod.ADVERSARIAL_ROBUSTNESS not in by_method
    assert by_method[TrainingMethod.CAUSAL_LANGUAGE_MODELING] >= 1
    assert by_method[TrainingMethod.SELF_SUPERVISED_SPAN] >= 1
    assert sum(by_method.values()) <= 10
    assert len(allocation.allocation_digest) == 64
    assert allocation.source_plan_digests == tuple(
        sorted(
            (
                _sha("plan-1"),
                _sha("plan-2"),
                _sha("plan-3"),
            )
        )
    )


def test_allocation_never_uses_promotion_holdout_as_training_oracle() -> None:
    with pytest.raises(
        TrainingAllocationError,
        match="development, regression or Mirror validation",
    ):
        _observation(
            TrainingMethod.SUPERVISED_INSTRUCTION,
            gain=1.0,
            compute=1.0,
            index=1,
            evaluation_class="promotion_holdout",
        )


def test_allocation_is_replay_deterministic() -> None:
    observations = (
        _observation(
            TrainingMethod.SUPERVISED_INSTRUCTION,
            gain=0.4,
            compute=1.0,
            index=1,
        ),
        _observation(
            TrainingMethod.DISTILLATION,
            gain=0.3,
            compute=0.5,
            index=2,
            evaluation_class="regression",
        ),
    )
    first = allocate_training_methods(observations)
    second = allocate_training_methods(tuple(reversed(observations)))
    assert first.allocation_digest == second.allocation_digest
    assert first.as_dict() == second.as_dict()


def _qualification_fixture():
    candidate_model = _sha("candidate-model")
    baseline_model = _sha("baseline-model")
    artifact = _sha("artifact")
    plan = _sha("training-plan")
    mirror_candidate_digest = _sha("mirror-candidate")
    mirror_baseline_digest = _sha("mirror-baseline")
    camera = _sha("camera")
    allocation = _sha("allocation")

    binding = MirrorModelBinding(
        candidate_model_digest=candidate_model,
        baseline_model_digest=baseline_model,
        candidate_artifact_sha256=artifact,
        training_plan_digest=plan,
        mirror_candidate_id="mirror-candidate-v2",
        mirror_candidate_digest=mirror_candidate_digest,
        mirror_baseline_candidate_id="mirror-baseline-v1",
        mirror_baseline_candidate_digest=mirror_baseline_digest,
        firewall_candidate_id="firewall:model-v2",
        camera_coverage_digest=camera,
        method_allocation_digest=allocation,
    )
    training_receipt = {
        "model_digest": candidate_model,
        "artifact_sha256": artifact,
        "training_plan": {
            "plan_digest": plan,
            "camera_coverage_digests": [camera],
        },
        "method_allocation": {"allocation_digest": allocation},
        "model_architecture": "gated_recurrent",
        "promotion_state": "candidate_only",
        "evaluation_manifest": {
            "candidate_model_digest": candidate_model,
            "candidate_artifact_sha256": artifact,
            "training_plan_digest": plan,
            "method_allocation_digest": allocation,
            "model_architecture": "gated_recurrent",
            "baseline": {"model_digest": baseline_model},
            "promotion_authority": False,
        },
    }
    mirror = SimpleNamespace(
        candidate_id="mirror-candidate-v2",
        candidate_digest=mirror_candidate_digest,
        baseline_candidate_id="mirror-baseline-v1",
        baseline_candidate_digest=mirror_baseline_digest,
        verifier_id="mirror-independent-verifier",
        production_authority=False,
        direct_self_modify=False,
        digest=_sha("mirror-evidence"),
    )
    firewall = SimpleNamespace(
        candidate_id="firewall:model-v2",
        evaluator_identity="evaluator:" + _sha("evaluator"),
        holdout_queries_used=1,
        holdout_query_budget=3,
        digest=_sha("firewall-evidence"),
    )
    return binding, training_receipt, mirror, firewall


def test_qualification_binds_training_mirror_firewall_for_lifecycle() -> None:
    binding, receipt, mirror, firewall = _qualification_fixture()
    qualified = qualify_learning_candidate(
        training_receipt=receipt,
        binding=binding,
        mirror_promotion_evidence=mirror,
        firewall_promotion_evidence=firewall,
    )

    assert qualified.candidate_model_digest == binding.candidate_model_digest
    assert qualified.baseline_model_digest == binding.baseline_model_digest
    assert qualified.production_authority is False
    assert qualified.direct_self_modify is False
    assert qualified.camera_coverage_digest == binding.camera_coverage_digest
    assert (
        qualified.method_allocation_digest
        == binding.method_allocation_digest
    )
    assert len(qualified.lifecycle_evidence_refs) == 6
    assert any(
        ref.startswith("mirror-room-evidence-sha256:")
        for ref in qualified.lifecycle_evidence_refs
    )
    assert any(
        ref.startswith("evaluation-firewall-evidence-sha256:")
        for ref in qualified.lifecycle_evidence_refs
    )
    assert len(qualified.qualification_digest) == 64
    lifecycle = qualified.lifecycle_validation_kwargs(
        verifier_id="lifecycle-independent-verifier"
    )
    assert lifecycle["model_digest"] == binding.candidate_model_digest
    assert lifecycle["verifier_id"] == "lifecycle-independent-verifier"
    assert lifecycle["evidence_refs"] == qualified.lifecycle_evidence_refs


def test_qualification_rejects_candidate_identity_drift() -> None:
    binding, receipt, mirror, firewall = _qualification_fixture()
    receipt = {
        **receipt,
        "model_digest": _sha("different-model"),
    }
    with pytest.raises(
        LearningQualificationError,
        match="candidate model identity drift",
    ):
        qualify_learning_candidate(
            training_receipt=receipt,
            binding=binding,
            mirror_promotion_evidence=mirror,
            firewall_promotion_evidence=firewall,
        )


def test_qualification_rejects_mirror_authority_escalation() -> None:
    binding, receipt, mirror, firewall = _qualification_fixture()
    mirror.production_authority = True
    with pytest.raises(
        LearningQualificationError,
        match="production authority",
    ):
        qualify_learning_candidate(
            training_receipt=receipt,
            binding=binding,
            mirror_promotion_evidence=mirror,
            firewall_promotion_evidence=firewall,
        )


def test_qualification_rejects_exhausted_or_invalid_holdout_budget() -> None:
    binding, receipt, mirror, firewall = _qualification_fixture()
    firewall.holdout_queries_used = 4
    with pytest.raises(
        LearningQualificationError,
        match="query budget evidence",
    ):
        qualify_learning_candidate(
            training_receipt=receipt,
            binding=binding,
            mirror_promotion_evidence=mirror,
            firewall_promotion_evidence=firewall,
        )



def test_qualification_rejects_method_allocation_identity_drift() -> None:
    binding, receipt, mirror, firewall = _qualification_fixture()
    receipt = {
        **receipt,
        "method_allocation": {
            "allocation_digest": _sha("different-allocation")
        },
    }
    with pytest.raises(
        LearningQualificationError,
        match="method allocation identity drift",
    ):
        qualify_learning_candidate(
            training_receipt=receipt,
            binding=binding,
            mirror_promotion_evidence=mirror,
            firewall_promotion_evidence=firewall,
        )


def test_mirror_validation_report_maps_to_holdout_safe_observation() -> None:
    scenario = SimpleNamespace(
        candidate_receipt=SimpleNamespace(
            outcome=SimpleNamespace(
                cost_units=0.0,
                tokens=500,
                steps=20,
            )
        )
    )
    report = SimpleNamespace(
        split=SimpleNamespace(value="validation"),
        weighted_utility_delta=0.25,
        digest=_sha("mirror-validation-report"),
        scenario_comparisons=(scenario, scenario),
    )

    observation = observe_mirror_validation(
        TrainingMethod.CONTRASTIVE,
        comparison_report=report,
        plan_digest=_sha("training-plan-source"),
    )

    assert observation.evaluation_class == "mirror_validation"
    assert observation.validation_gain == 0.25
    assert observation.sample_count == 2
    assert observation.compute_units > 0.0
    assert observation.evaluation_digest == report.digest


def test_mirror_holdout_cannot_feed_adaptive_method_selection() -> None:
    report = SimpleNamespace(
        split=SimpleNamespace(value="holdout"),
        weighted_utility_delta=1.0,
        digest=_sha("sealed-holdout"),
        scenario_comparisons=(SimpleNamespace(),),
    )
    with pytest.raises(
        TrainingAllocationError,
        match="only Mirror validation split",
    ):
        observe_mirror_validation(
            TrainingMethod.SUPERVISED_INSTRUCTION,
            comparison_report=report,
            plan_digest=_sha("source-plan"),
            compute_units=1.0,
        )


def test_qualification_rejects_training_baseline_drift() -> None:
    binding, receipt, mirror, firewall = _qualification_fixture()
    receipt = {
        **receipt,
        "evaluation_manifest": {
            **receipt["evaluation_manifest"],
            "baseline": {"model_digest": _sha("wrong-baseline")},
        },
    }
    with pytest.raises(
        LearningQualificationError,
        match="baseline identity drift",
    ):
        qualify_learning_candidate(
            training_receipt=receipt,
            binding=binding,
            mirror_promotion_evidence=mirror,
            firewall_promotion_evidence=firewall,
        )


def test_lifecycle_handoff_requires_third_independent_verifier() -> None:
    binding, receipt, mirror, firewall = _qualification_fixture()
    qualified = qualify_learning_candidate(
        training_receipt=receipt,
        binding=binding,
        mirror_promotion_evidence=mirror,
        firewall_promotion_evidence=firewall,
    )
    with pytest.raises(
        LearningQualificationError,
        match="explicit independent verifier",
    ):
        qualified.lifecycle_validation_kwargs()
    with pytest.raises(
        LearningQualificationError,
        match="differ from Mirror verifier",
    ):
        qualified.lifecycle_validation_kwargs(
            verifier_id=mirror.verifier_id,
        )


def test_qualification_rejects_camera_binding_drift() -> None:
    binding, receipt, mirror, firewall = _qualification_fixture()
    receipt = {
        **receipt,
        "training_plan": {
            **receipt["training_plan"],
            "camera_coverage_digests": [_sha("other-camera")],
        },
    }
    with pytest.raises(
        LearningQualificationError,
        match="camera coverage identity drift",
    ):
        qualify_learning_candidate(
            training_receipt=receipt,
            binding=binding,
            mirror_promotion_evidence=mirror,
            firewall_promotion_evidence=firewall,
        )


def test_qualification_rejects_promoted_training_receipt() -> None:
    binding, receipt, mirror, firewall = _qualification_fixture()
    receipt = {**receipt, "promotion_state": "active"}
    with pytest.raises(
        LearningQualificationError,
        match="candidate_only",
    ):
        qualify_learning_candidate(
            training_receipt=receipt,
            binding=binding,
            mirror_promotion_evidence=mirror,
            firewall_promotion_evidence=firewall,
        )


def test_allocation_rejects_duplicate_validation_receipt_replay() -> None:
    observation = _observation(
        TrainingMethod.SUPERVISED_INSTRUCTION,
        gain=0.4,
        compute=1.0,
        index=7,
    )
    with pytest.raises(
        TrainingAllocationError,
        match="duplicate validation observation evidence",
    ):
        allocate_training_methods((observation, observation))


def test_qualification_rejects_model_architecture_drift() -> None:
    binding, receipt, mirror, firewall = _qualification_fixture()
    receipt = {
        **receipt,
        "evaluation_manifest": {
            **receipt["evaluation_manifest"],
            "model_architecture": "elman_recurrent",
        },
    }
    with pytest.raises(
        LearningQualificationError,
        match="model architecture drift",
    ):
        qualify_learning_candidate(
            training_receipt=receipt,
            binding=binding,
            mirror_promotion_evidence=mirror,
            firewall_promotion_evidence=firewall,
        )


def test_real_mirror_and_firewall_evidence_qualify_candidate() -> None:
    binding, receipt, _mirror, _firewall = _qualification_fixture()

    evaluation_firewall = EvaluationFirewall()
    holdout = evaluation_firewall.register_set(
        EvaluationSet(
            set_id="reverse-product-holdout-v1",
            eval_class="promotion_holdout",
            content_digest=_sha("sealed-product-holdout"),
            population_id="standalone-ai-product-v1",
            query_budget=2,
            training_excluded=True,
            metadata={"sealed": True, "purpose": "candidate-promotion"},
        )
    )
    evaluator = evaluation_firewall.register_evaluator(
        EvaluatorIdentity(
            evaluator_id="reverse-product-independent-evaluator",
            implementation_digest=_sha("firewall-evaluator-implementation"),
            policy_digest=_sha("firewall-evaluator-policy"),
        )
    )
    evaluation_firewall.assert_training_exclusion(
        (
            "training-plan-sha256:" + binding.training_plan_digest,
            "learning-binding-sha256:" + binding.digest,
        )
    )
    query = evaluation_firewall.query(
        candidate_id=binding.firewall_candidate_id,
        set_id=holdout.set_id,
        evaluator_id=evaluator.evaluator_id,
        purpose="sealed-promotion-qualification",
    )
    firewall_evidence = evaluation_firewall.promotion_evidence(
        candidate_id=binding.firewall_candidate_id,
        holdout_set_id=holdout.set_id,
        evaluator_id=evaluator.evaluator_id,
    )
    assert firewall_evidence.query_receipt_digests == (query.digest,)
    assert firewall_evidence.holdout_queries_used == 1
    assert firewall_evidence.holdout_query_budget == 2

    mirror_evidence = MirrorPromotionEvidence(
        experiment_id="reverse-product-learning-v1",
        run_id="reverse-product-mirror-run-1",
        run_digest=_sha("mirror-run"),
        manifest_digest=_sha("mirror-manifest"),
        baseline_candidate_id=binding.mirror_baseline_candidate_id,
        baseline_candidate_digest=binding.mirror_baseline_candidate_digest,
        candidate_id=binding.mirror_candidate_id,
        candidate_digest=binding.mirror_candidate_digest,
        candidate_version="candidate-v2",
        generator_id="mirror-generator-v1",
        executor_id="mirror-sandbox-executor-v1",
        holdout_report_digest=_sha("mirror-holdout-report"),
        sealed_holdout_digest=_sha("mirror-sealed-holdout"),
        split_integrity_digest=_sha("mirror-split-integrity"),
        validation_report_digests=(
            _sha("mirror-validation-report"),
        ),
        verifier_id="mirror-independent-verifier",
        evaluation_refs=(
            "eval:mirror-validation:v1",
            "eval:mirror-holdout:v1",
        ),
        verified_at=1,
        rollback_candidate_id=binding.mirror_baseline_candidate_id,
        rollback_candidate_digest=binding.mirror_baseline_candidate_digest,
    )

    qualified = qualify_learning_candidate(
        training_receipt=receipt,
        binding=binding,
        mirror_promotion_evidence=mirror_evidence,
        firewall_promotion_evidence=firewall_evidence,
    )

    assert qualified.mirror_evidence_digest == mirror_evidence.digest
    assert qualified.firewall_evidence_digest == firewall_evidence.digest
    assert (
        qualified.firewall_evaluator_identity
        == firewall_evidence.evaluator_identity
    )
    assert qualified.production_authority is False
    assert qualified.direct_self_modify is False
    lifecycle = qualified.lifecycle_validation_kwargs(
        verifier_id="lifecycle-independent-verifier"
    )
    assert lifecycle["model_digest"] == binding.candidate_model_digest
    assert any(
        ref == "mirror-room-evidence-sha256:" + mirror_evidence.digest
        for ref in lifecycle["evidence_refs"]
    )
    assert any(
        ref
        == "evaluation-firewall-evidence-sha256:"
        + firewall_evidence.digest
        for ref in lifecycle["evidence_refs"]
    )
