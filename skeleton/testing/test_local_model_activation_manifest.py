from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from skeleton.ai.runtime.inference.artifact import (
    LocalModelArtifactError,
    local_model_adapter_from_env,
)
from skeleton.ai.runtime.inference.local import ReferenceNGramModel
from skeleton.ai.runtime.product.activation import (
    LocalModelActivationError,
    build_local_model_activation_manifest,
    load_local_model_activation_manifest,
    local_model_adapter_from_activation_manifest,
    write_local_model_activation_manifest,
)
from skeleton.ai.runtime.product.qualification import (
    LearningQualificationBundle,
)
from skeleton.learning.model_program import ModelPromotionReceipt


def _sha(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _payload_digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _write_ngram(path: Path, *, model_id: str, text: str):
    model = ReferenceNGramModel.train(
        (text, text),
        order=2,
        model_id=model_id,
    )
    raw = json.dumps(
        model.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    path.write_text(raw, encoding="utf-8")
    return model, _sha_bytes(path.read_bytes())


def _qualification(
    *,
    candidate_digest: str,
    candidate_artifact: str,
    baseline_digest: str,
) -> LearningQualificationBundle:
    binding = _sha("binding")
    plan = _sha("plan")
    mirror = _sha("mirror")
    firewall = _sha("firewall")
    refs = (
        "learning-binding-sha256:" + binding,
        "training-plan-sha256:" + plan,
        "mirror-room-evidence-sha256:" + mirror,
        "evaluation-firewall-evidence-sha256:" + firewall,
        "evaluation-holdout:evalset:" + _sha("holdout"),
    )
    payload = {
        "schema_version": "skeleton.learning_qualification.v1",
        "binding_digest": binding,
        "candidate_model_digest": candidate_digest,
        "baseline_model_digest": baseline_digest,
        "candidate_artifact_sha256": candidate_artifact,
        "training_plan_digest": plan,
        "mirror_evidence_digest": mirror,
        "firewall_evidence_digest": firewall,
        "mirror_verifier_id": "mirror-verifier",
        "firewall_evaluator_identity": "evaluator:" + _sha("evaluator"),
        "lifecycle_evidence_refs": list(refs),
        "camera_coverage_digest": None,
        "method_allocation_digest": None,
        "production_authority": False,
        "direct_self_modify": False,
    }
    return LearningQualificationBundle(
        binding_digest=binding,
        candidate_model_digest=candidate_digest,
        baseline_model_digest=baseline_digest,
        candidate_artifact_sha256=candidate_artifact,
        training_plan_digest=plan,
        mirror_evidence_digest=mirror,
        firewall_evidence_digest=firewall,
        mirror_verifier_id="mirror-verifier",
        firewall_evaluator_identity="evaluator:" + _sha("evaluator"),
        lifecycle_evidence_refs=refs,
        camera_coverage_digest=None,
        method_allocation_digest=None,
        production_authority=False,
        direct_self_modify=False,
        qualification_digest=_payload_digest(payload),
    )


def _promotion(
    *,
    model_id: str,
    model_digest: str,
    qualification: LearningQualificationBundle,
    bridge_digest: str,
) -> ModelPromotionReceipt:
    refs = (
        *qualification.lifecycle_evidence_refs,
        "learning-qualification-sha256:"
        + qualification.qualification_digest,
        "model-program-bridge-sha256:" + bridge_digest,
    )
    return ModelPromotionReceipt(
        model_id=model_id,
        model_digest=model_digest,
        training_receipt_digest=_sha("training-receipt"),
        evaluation_refs=refs,
        verifier_id="promotion-independent-verifier",
    )


def test_activation_manifest_binds_candidate_baseline_and_promotion(
    tmp_path: Path,
) -> None:
    baseline_path = tmp_path / "baseline.json"
    candidate_path = tmp_path / "candidate.json"
    baseline, baseline_sha = _write_ngram(
        baseline_path,
        model_id="baseline-v1",
        text="baseline stable answer",
    )
    candidate, candidate_sha = _write_ngram(
        candidate_path,
        model_id="candidate-v2",
        text="candidate improved answer",
    )
    bridge_digest = _sha("model-program-bridge")
    qualification = _qualification(
        candidate_digest=candidate.model_digest,
        candidate_artifact=candidate_sha,
        baseline_digest=baseline.model_digest,
    )
    promotion = _promotion(
        model_id=candidate.model_id,
        model_digest=candidate.model_digest,
        qualification=qualification,
        bridge_digest=bridge_digest,
    )

    manifest = build_local_model_activation_manifest(
        candidate_path=candidate_path,
        baseline_path=baseline_path,
        promotion_receipt=promotion,
        qualification=qualification,
        model_program_bridge_digest=bridge_digest,
        operator_authorization_ref="operator-approval:local-model:v2",
        cache_size=7,
        default_seed=19,
    )

    assert manifest.candidate_artifact_sha256 == candidate_sha
    assert manifest.candidate_model_digest == candidate.model_digest
    assert manifest.baseline_artifact_sha256 == baseline_sha
    assert manifest.baseline_model_digest == baseline.model_digest
    assert manifest.promotion_receipt_digest == promotion.digest
    assert manifest.qualification_digest == qualification.qualification_digest
    assert manifest.rollback_required is True
    assert manifest.direct_self_modify is False
    assert manifest.rollback_target()["model_digest"] == baseline.model_digest


def test_written_activation_requires_exact_deployment_digest(
    tmp_path: Path,
) -> None:
    baseline_path = tmp_path / "baseline.json"
    candidate_path = tmp_path / "candidate.json"
    baseline, _ = _write_ngram(
        baseline_path,
        model_id="baseline-v1",
        text="baseline stable answer",
    )
    candidate, candidate_sha = _write_ngram(
        candidate_path,
        model_id="candidate-v2",
        text="candidate improved answer",
    )
    bridge_digest = _sha("bridge")
    qualification = _qualification(
        candidate_digest=candidate.model_digest,
        candidate_artifact=candidate_sha,
        baseline_digest=baseline.model_digest,
    )
    promotion = _promotion(
        model_id=candidate.model_id,
        model_digest=candidate.model_digest,
        qualification=qualification,
        bridge_digest=bridge_digest,
    )
    manifest = build_local_model_activation_manifest(
        candidate_path=candidate_path,
        baseline_path=baseline_path,
        promotion_receipt=promotion,
        qualification=qualification,
        model_program_bridge_digest=bridge_digest,
        operator_authorization_ref="operator-approval:test",
    )
    manifest_path = write_local_model_activation_manifest(
        manifest,
        tmp_path / "activation.json",
    )

    loaded = load_local_model_activation_manifest(
        manifest_path,
        expected_manifest_digest=manifest.manifest_digest,
    )
    assert loaded.candidate.receipt.model_digest == candidate.model_digest
    assert loaded.baseline.receipt.model_digest == baseline.model_digest

    with pytest.raises(
        LocalModelActivationError,
        match="deployment-pinned",
    ):
        load_local_model_activation_manifest(
            manifest_path,
            expected_manifest_digest="0" * 64,
        )


def test_activation_rejects_candidate_artifact_tamper(
    tmp_path: Path,
) -> None:
    baseline_path = tmp_path / "baseline.json"
    candidate_path = tmp_path / "candidate.json"
    baseline, _ = _write_ngram(
        baseline_path,
        model_id="baseline-v1",
        text="baseline stable answer",
    )
    candidate, candidate_sha = _write_ngram(
        candidate_path,
        model_id="candidate-v2",
        text="candidate improved answer",
    )
    bridge_digest = _sha("bridge-tamper")
    qualification = _qualification(
        candidate_digest=candidate.model_digest,
        candidate_artifact=candidate_sha,
        baseline_digest=baseline.model_digest,
    )
    promotion = _promotion(
        model_id=candidate.model_id,
        model_digest=candidate.model_digest,
        qualification=qualification,
        bridge_digest=bridge_digest,
    )
    manifest = build_local_model_activation_manifest(
        candidate_path=candidate_path,
        baseline_path=baseline_path,
        promotion_receipt=promotion,
        qualification=qualification,
        model_program_bridge_digest=bridge_digest,
        operator_authorization_ref="operator-approval:tamper",
    )
    manifest_path = write_local_model_activation_manifest(
        manifest,
        tmp_path / "activation.json",
    )
    candidate_path.write_text(
        candidate_path.read_text(encoding="utf-8") + " ",
        encoding="utf-8",
    )

    with pytest.raises(
        LocalModelActivationError,
        match="candidate artifact identity drift",
    ):
        load_local_model_activation_manifest(
            manifest_path,
            expected_manifest_digest=manifest.manifest_digest,
        )


def test_activation_rejects_wrong_rollback_baseline(
    tmp_path: Path,
) -> None:
    baseline_path = tmp_path / "baseline.json"
    candidate_path = tmp_path / "candidate.json"
    _baseline, _ = _write_ngram(
        baseline_path,
        model_id="baseline-v1",
        text="baseline stable answer",
    )
    candidate, candidate_sha = _write_ngram(
        candidate_path,
        model_id="candidate-v2",
        text="candidate improved answer",
    )
    bridge_digest = _sha("bridge-baseline")
    qualification = _qualification(
        candidate_digest=candidate.model_digest,
        candidate_artifact=candidate_sha,
        baseline_digest=_sha("not-the-loaded-baseline"),
    )
    promotion = _promotion(
        model_id=candidate.model_id,
        model_digest=candidate.model_digest,
        qualification=qualification,
        bridge_digest=bridge_digest,
    )

    with pytest.raises(
        LocalModelActivationError,
        match="does not bind rollback baseline",
    ):
        build_local_model_activation_manifest(
            candidate_path=candidate_path,
            baseline_path=baseline_path,
            promotion_receipt=promotion,
            qualification=qualification,
            model_program_bridge_digest=bridge_digest,
            operator_authorization_ref="operator-approval:wrong-baseline",
        )



def test_activation_manifest_executes_authenticated_rollback_target(
    tmp_path: Path,
) -> None:
    baseline_path = tmp_path / "baseline.json"
    candidate_path = tmp_path / "candidate.json"
    baseline, _ = _write_ngram(
        baseline_path,
        model_id="baseline-v1",
        text="baseline rollback answer",
    )
    candidate, candidate_sha = _write_ngram(
        candidate_path,
        model_id="candidate-v2",
        text="candidate improved answer",
    )
    bridge_digest = _sha("bridge-rollback")
    qualification = _qualification(
        candidate_digest=candidate.model_digest,
        candidate_artifact=candidate_sha,
        baseline_digest=baseline.model_digest,
    )
    promotion = _promotion(
        model_id=candidate.model_id,
        model_digest=candidate.model_digest,
        qualification=qualification,
        bridge_digest=bridge_digest,
    )
    manifest = build_local_model_activation_manifest(
        candidate_path=candidate_path,
        baseline_path=baseline_path,
        promotion_receipt=promotion,
        qualification=qualification,
        model_program_bridge_digest=bridge_digest,
        operator_authorization_ref="operator-approval:rollback",
        cache_size=0,
    )
    manifest_path = write_local_model_activation_manifest(
        manifest,
        tmp_path / "activation-rollback.json",
    )

    adapter = local_model_adapter_from_activation_manifest(
        manifest_path,
        expected_manifest_digest=manifest.manifest_digest,
        target="rollback",
    )

    assert adapter.activation_target == "rollback"
    assert adapter.artifact_receipt.model_digest == baseline.model_digest
    assert adapter.activation_manifest.manifest_digest == manifest.manifest_digest


def test_environment_can_select_digest_pinned_rollback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    baseline_path = tmp_path / "baseline.json"
    candidate_path = tmp_path / "candidate.json"
    baseline, _ = _write_ngram(
        baseline_path,
        model_id="baseline-v1",
        text="baseline rollback answer",
    )
    candidate, candidate_sha = _write_ngram(
        candidate_path,
        model_id="candidate-v2",
        text="candidate improved answer",
    )
    bridge_digest = _sha("bridge-env-rollback")
    qualification = _qualification(
        candidate_digest=candidate.model_digest,
        candidate_artifact=candidate_sha,
        baseline_digest=baseline.model_digest,
    )
    promotion = _promotion(
        model_id=candidate.model_id,
        model_digest=candidate.model_digest,
        qualification=qualification,
        bridge_digest=bridge_digest,
    )
    manifest = build_local_model_activation_manifest(
        candidate_path=candidate_path,
        baseline_path=baseline_path,
        promotion_receipt=promotion,
        qualification=qualification,
        model_program_bridge_digest=bridge_digest,
        operator_authorization_ref="operator-approval:env-rollback",
        cache_size=0,
        default_seed=7,
    )
    manifest_path = write_local_model_activation_manifest(
        manifest,
        tmp_path / "activation-env-rollback.json",
    )

    monkeypatch.setenv("AI_LOCAL_ACTIVATION_MANIFEST", str(manifest_path))
    monkeypatch.setenv("AI_LOCAL_ACTIVATION_DIGEST", manifest.manifest_digest)
    monkeypatch.setenv("AI_LOCAL_ACTIVATION_TARGET", "rollback")
    monkeypatch.delenv("AI_LOCAL_MODEL_PATH", raising=False)

    adapter = local_model_adapter_from_env()

    assert adapter.activation_target == "rollback"
    assert adapter.artifact_receipt.model_digest == baseline.model_digest


def test_activation_target_fails_closed_without_manifest(
    monkeypatch,
) -> None:
    monkeypatch.delenv("AI_LOCAL_ACTIVATION_MANIFEST", raising=False)
    monkeypatch.delenv("AI_LOCAL_ACTIVATION_DIGEST", raising=False)
    monkeypatch.setenv("AI_LOCAL_ACTIVATION_TARGET", "rollback")
    monkeypatch.setenv("AI_LOCAL_MODEL_PATH", "/tmp/unused-local-model.json")

    with pytest.raises(
        LocalModelArtifactError,
        match="requires an activation manifest",
    ):
        local_model_adapter_from_env()
