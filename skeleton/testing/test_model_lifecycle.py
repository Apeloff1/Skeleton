from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from skeleton.ai.runtime.inference.local import ReferenceNGramModel
from skeleton.ai.runtime.product.activation import (
    LocalModelActivationManifest,
    build_local_model_activation_manifest,
)
from skeleton.ai.runtime.product.lifecycle import (
    ModelLifecycleError,
    ModelLifecycleRegistry,
    ModelLifecycleState,
    ModelLifecycleTransitionReceipt,
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


def _fixture(
    tmp_path: Path,
) -> tuple[
    Path,
    Path,
    BridgedModelProgramArtifact,
    LearningQualificationBundle,
    ModelPromotionReceipt,
]:
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
    return (
        baseline_path,
        candidate_path,
        bridged,
        qualification,
        promotion,
    )


def _activation(
    *,
    baseline_path: Path,
    candidate_path: Path,
    bridged: BridgedModelProgramArtifact,
    qualification: LearningQualificationBundle,
    promotion: ModelPromotionReceipt,
    promoted_transition: ModelLifecycleTransitionReceipt,
) -> LocalModelActivationManifest:
    return build_local_model_activation_manifest(
        candidate_path=candidate_path,
        baseline_path=baseline_path,
        promotion_receipt=promotion,
        qualification=qualification,
        lifecycle_promotion_transition=promoted_transition,
        model_program_bridge_digest=bridged.bridge_digest,
        operator_authorization_ref="operator-approval:lifecycle-v2",
        cache_size=0,
        default_seed=11,
    )


def _promote(
    registry: ModelLifecycleRegistry,
    bridged: BridgedModelProgramArtifact,
    qualification: LearningQualificationBundle,
    promotion: ModelPromotionReceipt,
    *,
    validation_verifier: str = "lifecycle-validation-verifier",
) -> ModelLifecycleTransitionReceipt:
    registry.register_candidate(
        bridged,
        authority_id="training-registration-authority",
    )
    registry.validate(
        bridged.artifact.model_digest,
        qualification,
        verifier_id=validation_verifier,
    )
    return registry.promote(bridged.artifact.model_digest, promotion)


def test_model_lifecycle_orders_candidate_to_activation_and_rollback(
    tmp_path: Path,
) -> None:
    (
        baseline_path,
        candidate_path,
        bridged,
        qualification,
        promotion,
    ) = _fixture(tmp_path)
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

    activation = _activation(
        baseline_path=baseline_path,
        candidate_path=candidate_path,
        bridged=bridged,
        qualification=qualification,
        promotion=promotion,
        promoted_transition=promoted,
    )
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
    assert snapshot.promotion_transition_digest == promoted.digest
    assert (
        snapshot.activation_manifest_digest
        == activation.manifest_digest
    )
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
    _, _, bridged, _qualification, promotion = _fixture(tmp_path)
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
    _, _, bridged, qualification, _promotion = _fixture(tmp_path)
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
    (
        baseline_path,
        candidate_path,
        bridged,
        qualification,
        promotion,
    ) = _fixture(tmp_path)

    staging = ModelLifecycleRegistry()
    staging_promoted = _promote(
        staging,
        bridged,
        qualification,
        promotion,
        validation_verifier="staging-lifecycle-validator",
    )
    activation = _activation(
        baseline_path=baseline_path,
        candidate_path=candidate_path,
        bridged=bridged,
        qualification=qualification,
        promotion=promotion,
        promoted_transition=staging_promoted,
    )

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
    (
        baseline_path,
        candidate_path,
        bridged,
        qualification,
        promotion,
    ) = _fixture(tmp_path)
    registry = ModelLifecycleRegistry()
    promoted = _promote(
        registry,
        bridged,
        qualification,
        promotion,
    )
    activation = _activation(
        baseline_path=baseline_path,
        candidate_path=candidate_path,
        bridged=bridged,
        qualification=qualification,
        promotion=promotion,
        promoted_transition=promoted,
    )

    with pytest.raises(
        ModelLifecycleError,
        match="deployment authority must be independent",
    ):
        registry.activate(
            bridged.artifact.model_digest,
            activation,
            deployment_authority_id=promotion.verifier_id,
        )


def test_lifecycle_rejects_manifest_from_other_promotion_chain(
    tmp_path: Path,
) -> None:
    (
        baseline_path,
        candidate_path,
        bridged,
        qualification,
        promotion,
    ) = _fixture(tmp_path)

    other = ModelLifecycleRegistry()
    other_promoted = _promote(
        other,
        bridged,
        qualification,
        promotion,
        validation_verifier="other-lifecycle-validator",
    )
    activation = _activation(
        baseline_path=baseline_path,
        candidate_path=candidate_path,
        bridged=bridged,
        qualification=qualification,
        promotion=promotion,
        promoted_transition=other_promoted,
    )

    registry = ModelLifecycleRegistry()
    promoted = _promote(
        registry,
        bridged,
        qualification,
        promotion,
        validation_verifier="canonical-lifecycle-validator",
    )
    assert promoted.digest != other_promoted.digest
    with pytest.raises(
        ModelLifecycleError,
        match="lifecycle promotion transition drift",
    ):
        registry.activate(
            bridged.artifact.model_digest,
            activation,
            deployment_authority_id="deployment-authority",
        )


def test_lifecycle_state_survives_restart_and_can_roll_back(
    tmp_path: Path,
) -> None:
    (
        baseline_path,
        candidate_path,
        bridged,
        qualification,
        promotion,
    ) = _fixture(tmp_path)
    state_path = tmp_path / "model-lifecycle.json"
    registry = ModelLifecycleRegistry(state_path)
    promoted = _promote(
        registry,
        bridged,
        qualification,
        promotion,
    )
    activation = _activation(
        baseline_path=baseline_path,
        candidate_path=candidate_path,
        bridged=bridged,
        qualification=qualification,
        promotion=promotion,
        promoted_transition=promoted,
    )
    registry.activate(
        bridged.artifact.model_digest,
        activation,
        deployment_authority_id="deployment-authority",
    )
    before = registry.snapshot(bridged.artifact.model_digest)
    history_before = tuple(
        item.digest
        for item in registry.history(bridged.artifact.model_digest)
    )
    state_digest = registry.state_digest()

    reopened = ModelLifecycleRegistry(state_path)
    restored = reopened.snapshot(bridged.artifact.model_digest)
    assert restored.state is ModelLifecycleState.ACTIVATED
    assert restored.digest == before.digest
    assert reopened.state_digest() == state_digest
    assert tuple(
        item.digest
        for item in reopened.history(bridged.artifact.model_digest)
    ) == history_before
    assert reopened.verify_history(bridged.artifact.model_digest) is True

    reopened.rollback(
        bridged.artifact.model_digest,
        activation,
        deployment_authority_id="deployment-authority",
    )
    after = ModelLifecycleRegistry(state_path)
    assert (
        after.snapshot(bridged.artifact.model_digest).state
        is ModelLifecycleState.ROLLED_BACK
    )
    assert len(after.history(bridged.artifact.model_digest)) == 5
    assert after.verify_history(bridged.artifact.model_digest) is True


def test_lifecycle_state_tamper_fails_closed(
    tmp_path: Path,
) -> None:
    _, _, bridged, _qualification, _promotion = _fixture(tmp_path)
    state_path = tmp_path / "model-lifecycle.json"
    registry = ModelLifecycleRegistry(state_path)
    registry.register_candidate(
        bridged,
        authority_id="training-registration-authority",
    )

    payload = json.loads(state_path.read_text(encoding="utf-8"))
    payload["records"][0]["trainer_id"] = "forged-training-authority"
    state_path.write_text(
        json.dumps(payload, sort_keys=True),
        encoding="utf-8",
    )

    with pytest.raises(
        ModelLifecycleError,
        match="state digest mismatch",
    ):
        ModelLifecycleRegistry(state_path)


def _fail_lifecycle_persist() -> None:
    raise ModelLifecycleError("injected lifecycle persistence failure")


def test_candidate_registration_rolls_back_memory_when_persist_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _, _, bridged, _qualification, _promotion = _fixture(tmp_path)
    state_path = tmp_path / "candidate-failure.json"
    registry = ModelLifecycleRegistry(state_path)
    monkeypatch.setattr(registry, "_persist", _fail_lifecycle_persist)

    with pytest.raises(
        ModelLifecycleError,
        match="injected lifecycle persistence failure",
    ):
        registry.register_candidate(
            bridged,
            authority_id="training-registration-authority",
        )

    with pytest.raises(
        ModelLifecycleError,
        match="not registered",
    ):
        registry.snapshot(bridged.artifact.model_digest)
    assert not state_path.exists()


def test_validation_rolls_back_memory_when_persist_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _, _, bridged, qualification, _promotion = _fixture(tmp_path)
    state_path = tmp_path / "validation-failure.json"
    registry = ModelLifecycleRegistry(state_path)
    registry.register_candidate(
        bridged,
        authority_id="training-registration-authority",
    )
    before = registry.snapshot(bridged.artifact.model_digest)
    durable_before = state_path.read_bytes()
    monkeypatch.setattr(registry, "_persist", _fail_lifecycle_persist)

    with pytest.raises(
        ModelLifecycleError,
        match="injected lifecycle persistence failure",
    ):
        registry.validate(
            bridged.artifact.model_digest,
            qualification,
            verifier_id="lifecycle-validation-verifier",
        )

    after = registry.snapshot(bridged.artifact.model_digest)
    assert after.state is ModelLifecycleState.CANDIDATE
    assert after.digest == before.digest
    assert registry.verify_history(bridged.artifact.model_digest) is True
    assert state_path.read_bytes() == durable_before


def test_promotion_rolls_back_memory_when_persist_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _, _, bridged, qualification, promotion = _fixture(tmp_path)
    state_path = tmp_path / "promotion-failure.json"
    registry = ModelLifecycleRegistry(state_path)
    registry.register_candidate(
        bridged,
        authority_id="training-registration-authority",
    )
    registry.validate(
        bridged.artifact.model_digest,
        qualification,
        verifier_id="lifecycle-validation-verifier",
    )
    before = registry.snapshot(bridged.artifact.model_digest)
    durable_before = state_path.read_bytes()
    monkeypatch.setattr(registry, "_persist", _fail_lifecycle_persist)

    with pytest.raises(
        ModelLifecycleError,
        match="injected lifecycle persistence failure",
    ):
        registry.promote(
            bridged.artifact.model_digest,
            promotion,
        )

    after = registry.snapshot(bridged.artifact.model_digest)
    assert after.state is ModelLifecycleState.VALIDATED
    assert after.digest == before.digest
    assert registry.verify_history(bridged.artifact.model_digest) is True
    assert state_path.read_bytes() == durable_before


def test_activation_rolls_back_memory_when_persist_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (
        baseline_path,
        candidate_path,
        bridged,
        qualification,
        promotion,
    ) = _fixture(tmp_path)
    state_path = tmp_path / "activation-failure.json"
    registry = ModelLifecycleRegistry(state_path)
    promoted = _promote(
        registry,
        bridged,
        qualification,
        promotion,
    )
    activation = _activation(
        baseline_path=baseline_path,
        candidate_path=candidate_path,
        bridged=bridged,
        qualification=qualification,
        promotion=promotion,
        promoted_transition=promoted,
    )
    before = registry.snapshot(bridged.artifact.model_digest)
    durable_before = state_path.read_bytes()
    monkeypatch.setattr(registry, "_persist", _fail_lifecycle_persist)

    with pytest.raises(
        ModelLifecycleError,
        match="injected lifecycle persistence failure",
    ):
        registry.activate(
            bridged.artifact.model_digest,
            activation,
            deployment_authority_id="deployment-authority",
        )

    after = registry.snapshot(bridged.artifact.model_digest)
    assert after.state is ModelLifecycleState.PROMOTED
    assert after.digest == before.digest
    assert registry.verify_history(bridged.artifact.model_digest) is True
    assert state_path.read_bytes() == durable_before


def test_rollback_rolls_back_memory_when_persist_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (
        baseline_path,
        candidate_path,
        bridged,
        qualification,
        promotion,
    ) = _fixture(tmp_path)
    state_path = tmp_path / "rollback-failure.json"
    registry = ModelLifecycleRegistry(state_path)
    promoted = _promote(
        registry,
        bridged,
        qualification,
        promotion,
    )
    activation = _activation(
        baseline_path=baseline_path,
        candidate_path=candidate_path,
        bridged=bridged,
        qualification=qualification,
        promotion=promotion,
        promoted_transition=promoted,
    )
    registry.activate(
        bridged.artifact.model_digest,
        activation,
        deployment_authority_id="deployment-authority",
    )
    before = registry.snapshot(bridged.artifact.model_digest)
    durable_before = state_path.read_bytes()
    monkeypatch.setattr(registry, "_persist", _fail_lifecycle_persist)

    with pytest.raises(
        ModelLifecycleError,
        match="injected lifecycle persistence failure",
    ):
        registry.rollback(
            bridged.artifact.model_digest,
            activation,
            deployment_authority_id="deployment-authority",
        )

    after = registry.snapshot(bridged.artifact.model_digest)
    assert after.state is ModelLifecycleState.ACTIVATED
    assert after.digest == before.digest
    assert registry.verify_history(bridged.artifact.model_digest) is True
    assert state_path.read_bytes() == durable_before
