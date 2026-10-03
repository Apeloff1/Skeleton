from __future__ import annotations

import hashlib
import json

import pytest

from skeleton.ai.runtime.inference.train import (
    build_multi_method_recurrent_artifact,
)
from skeleton.ai.runtime.inference.training_methods import TrainingExample
from skeleton.ai.runtime.product.model_program_bridge import (
    ModelProgramBridgeError,
    bridge_product_training_to_model_program,
    model_promotion_receipt_from_qualification,
)
from skeleton.ai.runtime.product.qualification import (
    LearningQualificationBundle,
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _product_receipt(tmp_path):
    pytest.importorskip("numpy")
    output = tmp_path / "bridged-model.json"
    receipt = build_multi_method_recurrent_artifact(
        examples=(
            TrainingExample(
                example_id="bridge-example",
                prompt="State the deterministic answer.",
                response="Use the verified local path.",
            ),
        ),
        output_path=output,
        model_id="bridged-local-model",
        hidden_size=8,
        epochs=1,
        learning_rate=0.03,
        max_vocab=48,
        max_document_tokens=64,
        seed=5,
        temperature=0.7,
    )
    receipt["promotion_state"] = "candidate_only"
    receipt["learning_candidate_digest"] = _sha("learning-candidate")
    receipt["method_allocation"] = None
    return receipt


def test_reverse_training_bridges_to_canonical_model_program(tmp_path) -> None:
    receipt = _product_receipt(tmp_path)

    bridged = bridge_product_training_to_model_program(
        receipt,
        run_id="reverse-run-1",
        trainer_id="skeleton.reverse-multimethod-trainer.v1",
        code_revision="test-revision",
    )

    assert bridged.artifact.model_id == receipt["model_id"]
    assert bridged.artifact.model_digest == receipt["model_digest"]
    assert bridged.artifact.artifact_digest == receipt["artifact_sha256"]
    assert (
        bridged.training_receipt.dataset_digests
        == (receipt["training_plan"]["corpus_digest"],)
    )
    assert (
        bridged.training_receipt.model_digest
        == bridged.artifact.model_digest
    )
    assert bridged.training_receipt.digest
    assert bridged.training_receipt.metrics["optimizer_steps"] > 0
    assert (
        bridged.training_receipt.metrics["gradient_accumulation_steps"]
        == 4.0
    )
    assert len(bridged.bridge_digest) == 64


def _qualification_for(bridged) -> LearningQualificationBundle:
    refs = (
        "learning-binding-sha256:" + _sha("binding-ref"),
        "training-plan-sha256:" + bridged.training_plan_digest,
        "mirror-room-evidence-sha256:" + _sha("mirror-ref"),
        "evaluation-firewall-evidence-sha256:" + _sha("firewall-ref"),
    )
    payload = {
        "schema_version": "skeleton.learning_qualification.v1",
        "binding_digest": _sha("binding"),
        "candidate_model_digest": bridged.artifact.model_digest,
        "baseline_model_digest": _sha("baseline-model"),
        "candidate_artifact_sha256": bridged.artifact.artifact_digest,
        "training_plan_digest": bridged.training_plan_digest,
        "mirror_evidence_digest": _sha("mirror-evidence"),
        "firewall_evidence_digest": _sha("firewall-evidence"),
        "mirror_verifier_id": "mirror-independent-verifier",
        "firewall_evaluator_identity": "firewall-independent-evaluator",
        "lifecycle_evidence_refs": list(refs),
        "camera_coverage_digest": None,
        "method_allocation_digest": None,
        "production_authority": False,
        "direct_self_modify": False,
    }
    digest = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return LearningQualificationBundle(
        **payload,
        qualification_digest=digest,
    )


def test_qualified_bridge_emits_canonical_model_promotion_receipt(
    tmp_path,
) -> None:
    bridged = bridge_product_training_to_model_program(
        _product_receipt(tmp_path),
        run_id="reverse-run-2",
        trainer_id="skeleton.reverse-multimethod-trainer.v1",
        code_revision="test-revision",
    )
    qualification = _qualification_for(bridged)

    promotion = model_promotion_receipt_from_qualification(
        bridged,
        qualification,
        verifier_id="model-promotion-independent-verifier",
    )

    assert promotion.model_id == bridged.artifact.model_id
    assert promotion.model_digest == bridged.artifact.model_digest
    assert (
        promotion.training_receipt_digest
        == bridged.training_receipt.digest
    )
    assert len(promotion.evaluation_refs) >= 6
    assert any(
        ref.startswith("learning-qualification-sha256:")
        for ref in promotion.evaluation_refs
    )
    assert any(
        ref.startswith("model-program-bridge-sha256:")
        for ref in promotion.evaluation_refs
    )
    assert len(promotion.digest) == 64


@pytest.mark.parametrize(
    "verifier_id",
    (
        "skeleton.reverse-multimethod-trainer.v1",
        "mirror-independent-verifier",
        "firewall-independent-evaluator",
    ),
)
def test_model_promotion_verifier_must_be_independent(
    tmp_path,
    verifier_id: str,
) -> None:
    bridged = bridge_product_training_to_model_program(
        _product_receipt(tmp_path),
        run_id="reverse-run-3",
        trainer_id="skeleton.reverse-multimethod-trainer.v1",
        code_revision="test-revision",
    )
    qualification = _qualification_for(bridged)

    with pytest.raises(
        ModelProgramBridgeError,
        match="must be independent",
    ):
        model_promotion_receipt_from_qualification(
            bridged,
            qualification,
            verifier_id=verifier_id,
        )


def test_bridge_rejects_non_candidate_product_receipt(tmp_path) -> None:
    receipt = _product_receipt(tmp_path)
    receipt["promotion_state"] = "active"

    with pytest.raises(
        ModelProgramBridgeError,
        match="candidate_only",
    ):
        bridge_product_training_to_model_program(
            receipt,
            run_id="reverse-run-4",
            trainer_id="skeleton.reverse-multimethod-trainer.v1",
            code_revision="test-revision",
        )
