from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from skeleton.ai.runtime.inference.local import ReferenceNGramModel
from skeleton.ai.runtime.product.activation import (
    build_local_model_activation_manifest,
)
from skeleton.ai.runtime.product.lifecycle import (
    ModelLifecycleError,
    ModelLifecycleRegistry,
    ModelLifecycleState,
)
from skeleton.ai.runtime.product.model_program_bridge import (
    BridgedModelProgramArtifact,
)
from skeleton.ai.runtime.product.qualification import (
    LearningQualificationBundle,
)
from skeleton.learning.model_program import (
    ModelArtifact,
    ModelPromotionReceipt,
    TrainingReceipt,
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _stable_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _write_model(
    path: Path,
    *,
    model_id: str,
    text: str,
) -> tuple[ReferenceNGramModel, dict[str, object], str]:
    model = ReferenceNGramModel.train(
        (text, text),
        order=2,
        model_id=model_id,
    )
    payload = model.to_dict()
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    path.write_text(raw, encoding="utf-8")
    return model, payload, hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path):
    baseline_path = tmp_path / "baseline.json"
    candidate_path = tmp_path / "candidate.json"
    baseline, _, _ = _write_model(
        baseline_path,
        model_id="lifecycle-baseline-v1",
        text="stable baseline behavior",
    )
    candidate, candidate_payload, candidate_sha = _write_model(
        candidate_path,
        model_id="lifecycle-candidate-v2",
        text="improved candidate behavior",
    )

    training = TrainingReceipt(
        run_id="lifecycle-training-run",
        spec_digest=_sha("spec"),
        dataset_digests=(_sha("dataset"),),
        trainer_id="training-authority",
        code_revision="test-revision",
        model_id=candidate.model_id,
        model_digest=candidate.model_digest,
        artifact_digest=candidate_sha,
        metrics={"documents": 2.0},
    )
    artifact = ModelArtifact(
        model_id=candidate.model_id,
        model_digest=candidate.model_digest,
        artifact_digest=candidate_sha,
        kind="reference_ngram",
        payload=candidate_payload,
        training_run_id=training.run_id,
    )
    bridged = BridgedModelProgramArtifact(
        artifact=artifact,
        training_receipt=training,
        training_plan_digest=_sha("training-plan"),
        corpus_digest=_sha("corpus"),
        learning_candidate_digest=_sha("learning-candidate"),
        source_receipt_digest=_sha("source-receipt"),
        bridge_digest=_sha("bridge"),
    )

    refs = (
        "learning-binding-sha256:" + _sha("binding"),
        "training-plan-sha256:" + bridged.training_plan_digest,
        "mirror-room-evidence-sha256:" + _sha("mirror-evidence"),
        "evaluation-firewall-evidence-sha256:" + _sha("firewall-evidence"),
        "evaluation-holdout:evalset:" + _sha("holdout"),
    )
    qualification_payload = {
        "schema_version": "skeleton.learning_qualification.v1",
        "binding_digest": _sha("binding"),
        "candidate_model_digest": candidate.model_digest,
        "baseline_model_digest": baseline.model_digest,
        "candidate_artifact_sha256": candidate_sha,
        "training_plan_digest": bridged.training_plan_digest,
        "mirror_evidence_digest": _sha("mirror-evidence"),
        "firewall_evidence_digest": _sha("firewall-evidence"),
        "mirror_verifier_id": "mirror-verifier",
        "firewall_evaluator_identity": "firewall-evaluator",
        "lifecycle_evidence_refs": list(refs),
        "camera_coverage_digest": None,
        "method_allocation_digest": None,
        "production_authority": False,
        "direct_self_modify": False,
    }
    qualification = LearningQualificationBundle(
        **{
            key: value
            for key, value in qualification_payload.items()
            if key != "schema_version"
        },
        qualification_digest=_stable_digest(qualification_payload),
    )
    promotion_refs = (
        *qualification.lifecycle_evidence_refs,
        "learning-qualification-sha256:"
        + qualification.qualification_digest,
        "model-program-bridge-sha256:" + bridged.bridge_digest,
    )
    promotion = ModelPromotionReceipt(
        model_id=candidate.model_id,
        model_digest=candidate.model_digest,
        training_receipt_digest=training.digest,
        evaluation_refs=promotion_refs,
        verifier_id="promotion-verifier",
    )
    activation = build_local_model_activation_manifest(
        candidate_path=candidate_path,
        baseline_path=baseline_path,
        promotion_receipt=promotion,
        qualification=qualification,
        model_program_bridge_digest=bridged.bridge_digest,
        operator_authorization_ref="operator-approval:lifecycle-v2",
        cache_size=0,
        default_seed=11,
    )
    return bridged, qualification, promotion, activation


def test_model_lifecycle_orders_candidate_to_activation_and_rollback(
    tmp_path: Path,
) -> None:
    bridged, qualification, promotion, activation = _fixture(tmp_path)
    registry = ModelLifecycleRegistry()

    candidate = registry.register_candidate(
        bridged,
        authority_id="training-registration-authority",
    )
    assert candidate.from_state is None
    assert candidate.to_state is ModelLifecycleState.CANDIDATE

    validated = registry.validate(
        bridged.artifact.model_digest,
        qualification,
        verifier_id="lifecycle-validation-verifier",
    )
    assert validated.from_state is ModelLifecycleState.CANDIDATE
    assert validated.to_state is ModelLifecycleState.VALIDATED

    promoted = registry.promote(
        bridged.artifact.model_digest,
        promotion,
    )
    assert promoted.from_state is ModelLifecycleState.VALIDATED
    assert promoted.to_state is ModelLifecycleState.PROMOTED

    activated = registry.activate(
        bridged.artifact.model_digest,
        activation,
        deployment_authority_id="deployment-authority",
    )
    assert activated.from_state is ModelLifecycleState.PROMOTED
    assert activated.to_state is ModelLifecycleState.ACTIVATED

    snapshot = registry.snapshot(bridged.artifact.model_digest)
    assert snapshot.state is ModelLifecycleState.ACTIVATED
    assert snapshot.transition_count == 4
    assert snapshot.activation_manifest_digest == activation.manifest_digest
    assert snapshot.rollback_model_digest == activation.baseline_model_digest
    assert registry.verify_history(bridged.artifact.model_digest) is True

    rolled_back = registry.rollback(
        bridged.artifact.model_digest,
        activation,
        deployment_authority_id="deployment-authority",
    )
    assert rolled_back.from_state is ModelLifecycleState.ACTIVATED
    assert rolled_back.to_state is ModelLifecycleState.ROLLED_BACK
    assert registry.snapshot(
        bridged.artifact.model_digest
    ).state is ModelLifecycleState.ROLLED_BACK
    assert registry.verify_history(bridged.artifact.model_digest) is True

    history = registry.history(bridged.artifact.model_digest)
    assert len(history) == 5
    assert all(
        right.prior_transition_digest == left.digest
        for left, right in zip(history, history[1:])
    )
    assert all(item.production_authority is False for item in history)
    assert all(item.direct_self_modify is False for item in history)


def test_lifecycle_rejects_skipping_validation(
    tmp_path: Path,
) -> None:
    bridged, _qualification, promotion, _activation = _fixture(tmp_path)
    registry = ModelLifecycleRegistry()
    registry.register_candidate(
        bridged,
        authority_id="training-registration-authority",
    )

    with pytest.raises(
        ModelLifecycleError,
        match="validated state",
    ):
        registry.promote(
            bridged.artifact.model_digest,
            promotion,
        )


def test_lifecycle_validation_requires_independent_authority(
    tmp_path: Path,
) -> None:
    bridged, qualification, _promotion, _activation = _fixture(tmp_path)
    registry = ModelLifecycleRegistry()
    registry.register_candidate(
        bridged,
        authority_id="training-registration-authority",
    )

    with pytest.raises(
        ModelLifecycleError,
        match="training authority cannot validate",
    ):
        registry.validate(
            bridged.artifact.model_digest,
            qualification,
            verifier_id=bridged.training_receipt.trainer_id,
        )


def test_lifecycle_rejects_activation_before_promotion(
    tmp_path: Path,
) -> None:
    bridged, qualification, _promotion, activation = _fixture(tmp_path)
    registry = ModelLifecycleRegistry()
    registry.register_candidate(
        bridged,
        authority_id="training-registration-authority",
    )
    registry.validate(
        bridged.artifact.model_digest,
        qualification,
        verifier_id="lifecycle-validation-verifier",
    )

    with pytest.raises(
        ModelLifecycleError,
        match="promoted state",
    ):
        registry.activate(
            bridged.artifact.model_digest,
            activation,
            deployment_authority_id="deployment-authority",
        )


def test_lifecycle_deployment_authority_is_independent(
    tmp_path: Path,
) -> None:
    bridged, qualification, promotion, activation = _fixture(tmp_path)
    registry = ModelLifecycleRegistry()
    registry.register_candidate(
        bridged,
        authority_id="training-registration-authority",
    )
    registry.validate(
        bridged.artifact.model_digest,
        qualification,
        verifier_id="lifecycle-validation-verifier",
    )
    registry.promote(bridged.artifact.model_digest, promotion)

    with pytest.raises(
        ModelLifecycleError,
        match="deployment authority must be independent",
    ):
        registry.activate(
            bridged.artifact.model_digest,
            activation,
            deployment_authority_id=promotion.verifier_id,
        )
