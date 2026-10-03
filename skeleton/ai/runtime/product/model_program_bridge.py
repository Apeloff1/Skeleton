"""Bridge reverse-trained local artifacts into the canonical model program.

The reverse product path trains a content-addressed local artifact and emits a
rich candidate receipt.  The canonical learning program owns typed
ModelArtifact, TrainingReceipt and ModelPromotionReceipt contracts.

This module binds the two without adding a second trainer or promotion
authority.  It only converts already-validated candidate evidence into the
canonical model-program types and still requires independent evaluation/
promotion evidence before a ModelPromotionReceipt can be produced.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Mapping

from skeleton.ai.runtime.inference.artifact import (
    LocalModelArtifactError,
    load_local_model_artifact,
)
from skeleton.learning.model_program import (
    ModelArtifact,
    ModelProgramError,
    ModelPromotionReceipt,
    TrainingReceipt,
)

from .qualification import LearningQualificationBundle


class ModelProgramBridgeError(RuntimeError):
    """Reverse-learning evidence cannot enter the canonical model program."""


def _stable_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ModelProgramBridgeError(
            "model-program bridge value is not deterministic JSON"
        ) from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _text(value: object, name: str, *, maximum: int = 1024) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ModelProgramBridgeError(f"{name} must be non-empty text")
    result = value.strip()
    if result != value or len(result) > maximum:
        raise ModelProgramBridgeError(f"{name} must be normalized text")
    return result


def _sha(value: object, name: str) -> str:
    result = _text(value, name, maximum=64).lower()
    if (
        len(result) != 64
        or any(ch not in "0123456789abcdef" for ch in result)
    ):
        raise ModelProgramBridgeError(f"{name} must be lowercase sha256")
    return result


def _positive_metric(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelProgramBridgeError(f"{name} must be numeric")
    result = float(value)
    if result < 0.0:
        raise ModelProgramBridgeError(f"{name} must be non-negative")
    return result


@dataclass(frozen=True, slots=True)
class BridgedModelProgramArtifact:
    """Exact canonical model-program identity for one reverse-trained candidate."""

    artifact: ModelArtifact
    training_receipt: TrainingReceipt
    training_plan_digest: str
    corpus_digest: str
    learning_candidate_digest: str
    source_receipt_digest: str
    bridge_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.artifact, ModelArtifact):
            raise TypeError("artifact must be ModelArtifact")
        if not isinstance(self.training_receipt, TrainingReceipt):
            raise TypeError("training_receipt must be TrainingReceipt")
        if self.artifact.model_id != self.training_receipt.model_id:
            raise ModelProgramBridgeError(
                "artifact and training receipt model id drift"
            )
        if self.artifact.model_digest != self.training_receipt.model_digest:
            raise ModelProgramBridgeError(
                "artifact and training receipt model digest drift"
            )
        if (
            self.artifact.artifact_digest
            != self.training_receipt.artifact_digest
        ):
            raise ModelProgramBridgeError(
                "artifact and training receipt artifact digest drift"
            )
        for name in (
            "training_plan_digest",
            "corpus_digest",
            "learning_candidate_digest",
            "source_receipt_digest",
            "bridge_digest",
        ):
            object.__setattr__(
                self,
                name,
                _sha(getattr(self, name), name),
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.product_model_program_bridge.v1",
            "model_id": self.artifact.model_id,
            "model_digest": self.artifact.model_digest,
            "artifact_digest": self.artifact.artifact_digest,
            "training_receipt_digest": self.training_receipt.digest,
            "training_plan_digest": self.training_plan_digest,
            "corpus_digest": self.corpus_digest,
            "learning_candidate_digest": self.learning_candidate_digest,
            "source_receipt_digest": self.source_receipt_digest,
            "bridge_digest": self.bridge_digest,
        }


def bridge_product_training_to_model_program(
    product_receipt: Mapping[str, object],
    *,
    run_id: str,
    trainer_id: str,
    code_revision: str,
) -> BridgedModelProgramArtifact:
    """Convert one verified reverse-training receipt to canonical program types."""

    if not isinstance(product_receipt, Mapping):
        raise TypeError("product_receipt must be a mapping")
    if product_receipt.get("promotion_state") != "candidate_only":
        raise ModelProgramBridgeError(
            "only candidate_only product receipts may enter model program"
        )

    run = _text(run_id, "run_id")
    trainer = _text(trainer_id, "trainer_id")
    revision = _text(code_revision, "code_revision", maximum=256)
    model_id = _text(product_receipt.get("model_id"), "model_id")
    model_digest = _sha(
        product_receipt.get("model_digest"),
        "model_digest",
    )
    artifact_digest = _sha(
        product_receipt.get("artifact_sha256"),
        "artifact_sha256",
    )
    learning_candidate_digest = _sha(
        product_receipt.get("learning_candidate_digest"),
        "learning_candidate_digest",
    )

    plan = product_receipt.get("training_plan")
    if not isinstance(plan, Mapping):
        raise ModelProgramBridgeError("product receipt lacks training_plan")
    plan_digest = _sha(plan.get("plan_digest"), "training plan digest")
    corpus_digest = _sha(plan.get("corpus_digest"), "training corpus digest")

    output_path = _text(
        product_receipt.get("output_path"),
        "output_path",
        maximum=4096,
    )
    path = Path(output_path).expanduser()
    try:
        loaded = load_local_model_artifact(path)
    except LocalModelArtifactError as exc:
        raise ModelProgramBridgeError(
            "product artifact cannot be authenticated"
        ) from exc
    if (
        loaded.receipt.model_id != model_id
        or loaded.receipt.model_digest != model_digest
        or loaded.receipt.artifact_sha256 != artifact_digest
    ):
        raise ModelProgramBridgeError(
            "product receipt identity differs from artifact bytes"
        )

    try:
        raw = path.resolve(strict=True).read_bytes()
    except OSError as exc:
        raise ModelProgramBridgeError(
            "product artifact bytes cannot be reread"
        ) from exc
    if hashlib.sha256(raw).hexdigest() != artifact_digest:
        raise ModelProgramBridgeError(
            "product artifact changed during bridge"
        )
    try:
        payload = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ModelProgramBridgeError(
            "product artifact is not canonical JSON"
        ) from exc
    if not isinstance(payload, Mapping):
        raise ModelProgramBridgeError(
            "product artifact root must be an object"
        )

    try:
        artifact = ModelArtifact(
            model_id=model_id,
            model_digest=model_digest,
            artifact_digest=artifact_digest,
            kind=loaded.receipt.schema,
            payload=dict(payload),
            training_run_id=run,
        )
    except ModelProgramError as exc:
        raise ModelProgramBridgeError(
            "artifact does not satisfy canonical model-program identity"
        ) from exc

    allocation = product_receipt.get("method_allocation")
    allocation_digest: str | None = None
    if allocation is not None:
        if not isinstance(allocation, Mapping):
            raise ModelProgramBridgeError(
                "method_allocation must be a mapping"
            )
        allocation_digest = _sha(
            allocation.get("allocation_digest"),
            "method allocation digest",
        )

    spec_digest = _digest(
        {
            "schema_version": "skeleton.reverse_training_spec.v1",
            "run_id": run,
            "trainer_id": trainer,
            "code_revision": revision,
            "model_id": model_id,
            "learning_candidate_digest": learning_candidate_digest,
            "training_plan_digest": plan_digest,
            "corpus_digest": corpus_digest,
            "method_allocation_digest": allocation_digest,
            "seed": product_receipt.get("seed"),
            "epochs": product_receipt.get("epochs"),
        }
    )

    metrics: dict[str, float] = {
        "documents": _positive_metric(
            plan.get("document_count"),
            "training document count",
        ),
        "total_chars": _positive_metric(
            plan.get("total_chars"),
            "training total chars",
        ),
        "training_tokens": _positive_metric(
            product_receipt.get("training_tokens", 0),
            "training_tokens",
        ),
        "epochs_completed": _positive_metric(
            product_receipt.get("epochs_completed", 0),
            "epochs_completed",
        ),
    }
    losses = product_receipt.get("training_loss_history", [])
    if not isinstance(losses, list):
        raise ModelProgramBridgeError(
            "training_loss_history must be a list"
        )
    if losses:
        final_loss = losses[-1]
        if isinstance(final_loss, bool) or not isinstance(
            final_loss,
            (int, float),
        ):
            raise ModelProgramBridgeError(
                "final training loss must be numeric"
            )
        metrics["final_loss"] = float(final_loss)

    training_receipt = TrainingReceipt(
        run_id=run,
        spec_digest=spec_digest,
        dataset_digests=(corpus_digest,),
        trainer_id=trainer,
        code_revision=revision,
        model_id=model_id,
        model_digest=model_digest,
        artifact_digest=artifact_digest,
        metrics=metrics,
    )
    source_receipt_digest = _digest(dict(product_receipt))
    bridge_payload = {
        "schema_version": "skeleton.product_model_program_bridge.v1",
        "model_id": model_id,
        "model_digest": model_digest,
        "artifact_digest": artifact_digest,
        "training_receipt_digest": training_receipt.digest,
        "training_plan_digest": plan_digest,
        "corpus_digest": corpus_digest,
        "learning_candidate_digest": learning_candidate_digest,
        "source_receipt_digest": source_receipt_digest,
    }
    return BridgedModelProgramArtifact(
        artifact=artifact,
        training_receipt=training_receipt,
        training_plan_digest=plan_digest,
        corpus_digest=corpus_digest,
        learning_candidate_digest=learning_candidate_digest,
        source_receipt_digest=source_receipt_digest,
        bridge_digest=_digest(bridge_payload),
    )


def model_promotion_receipt_from_qualification(
    bridged: BridgedModelProgramArtifact,
    qualification: LearningQualificationBundle,
    *,
    verifier_id: str,
) -> ModelPromotionReceipt:
    """Produce canonical model-promotion evidence from qualified candidate data.

    This creates evidence only. It does not change AI_LOCAL_MODEL_PATH or any
    production runtime state.
    """

    if not isinstance(bridged, BridgedModelProgramArtifact):
        raise TypeError("bridged must be BridgedModelProgramArtifact")
    if not isinstance(qualification, LearningQualificationBundle):
        raise TypeError(
            "qualification must be LearningQualificationBundle"
        )
    if (
        qualification.candidate_model_digest
        != bridged.artifact.model_digest
        or qualification.candidate_artifact_sha256
        != bridged.artifact.artifact_digest
        or qualification.training_plan_digest
        != bridged.training_plan_digest
    ):
        raise ModelProgramBridgeError(
            "qualification identity differs from bridged training artifact"
        )

    verifier = _text(verifier_id, "verifier_id")
    forbidden = {
        bridged.training_receipt.trainer_id,
        qualification.mirror_verifier_id,
        qualification.firewall_evaluator_identity,
    }
    if verifier in forbidden:
        raise ModelProgramBridgeError(
            "model promotion verifier must be independent of trainer and evaluators"
        )
    refs = (
        *qualification.lifecycle_evidence_refs,
        "learning-qualification-sha256:"
        + qualification.qualification_digest,
        "model-program-bridge-sha256:" + bridged.bridge_digest,
    )
    try:
        return ModelPromotionReceipt(
            model_id=bridged.artifact.model_id,
            model_digest=bridged.artifact.model_digest,
            training_receipt_digest=bridged.training_receipt.digest,
            evaluation_refs=refs,
            verifier_id=verifier,
        )
    except ModelProgramError as exc:
        raise ModelProgramBridgeError(
            "canonical model promotion receipt could not be constructed"
        ) from exc


__all__ = [
    "BridgedModelProgramArtifact",
    "ModelProgramBridgeError",
    "bridge_product_training_to_model_program",
    "model_promotion_receipt_from_qualification",
]
