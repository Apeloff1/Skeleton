"""Bridge native reverse training into canonical model-program evidence."""

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
    """Native training evidence cannot enter the canonical model program."""


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


def _text(value: object, name: str, *, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ModelProgramBridgeError(f"{name} must be non-empty text")
    result = value.strip()
    if result != value or len(result) > maximum:
        raise ModelProgramBridgeError(
            f"{name} must be normalized and bounded"
        )
    return result


def _sha(value: object, name: str) -> str:
    result = _text(value, name, maximum=64).lower()
    if (
        len(result) != 64
        or any(ch not in "0123456789abcdef" for ch in result)
    ):
        raise ModelProgramBridgeError(f"{name} must be lowercase sha256")
    return result


def _metric(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelProgramBridgeError(f"{name} must be numeric")
    result = float(value)
    if result < 0.0:
        raise ModelProgramBridgeError(f"{name} must be non-negative")
    return result


@dataclass(frozen=True, slots=True)
class BridgedModelProgramArtifact:
    artifact: ModelArtifact
    training_receipt: TrainingReceipt
    artifact_file_sha256: str
    native_training_receipt_digest: str
    corpus_digest: str
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
                "canonical artifact digest drift"
            )
        for name in (
            "artifact_file_sha256",
            "native_training_receipt_digest",
            "corpus_digest",
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
            "canonical_artifact_digest": self.artifact.artifact_digest,
            "artifact_file_sha256": self.artifact_file_sha256,
            "training_receipt_digest": self.training_receipt.digest,
            "native_training_receipt_digest": (
                self.native_training_receipt_digest
            ),
            "corpus_digest": self.corpus_digest,
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
    """Authenticate one native artifact and project it into canonical types."""

    if not isinstance(product_receipt, Mapping):
        raise TypeError("product_receipt must be a mapping")
    if product_receipt.get("credential_free") is not True:
        raise ModelProgramBridgeError(
            "bridge accepts only credential-free native training receipts"
        )

    run = _text(run_id, "run_id")
    trainer = _text(trainer_id, "trainer_id")
    revision = _text(code_revision, "code_revision", maximum=256)
    model_id = _text(product_receipt.get("model_id"), "model_id")
    model_digest = _sha(
        product_receipt.get("model_digest"),
        "model_digest",
    )
    artifact_file_sha = _sha(
        product_receipt.get("artifact_sha256"),
        "artifact_sha256",
    )
    native_receipt = _sha(
        product_receipt.get("training_receipt_digest"),
        "training_receipt_digest",
    )
    corpus_digest = _sha(
        product_receipt.get("corpus_digest"),
        "corpus_digest",
    )
    output_path = Path(
        _text(product_receipt.get("output_path"), "output_path")
    ).expanduser()

    try:
        loaded = load_local_model_artifact(output_path)
    except LocalModelArtifactError as exc:
        raise ModelProgramBridgeError(
            "native local artifact cannot be authenticated"
        ) from exc
    if (
        loaded.receipt.model_id != model_id
        or loaded.receipt.model_digest != model_digest
        or loaded.receipt.artifact_sha256 != artifact_file_sha
    ):
        raise ModelProgramBridgeError(
            "native training receipt differs from artifact bytes"
        )

    try:
        raw = output_path.resolve(strict=True).read_bytes()
        payload = json.loads(raw.decode("utf-8", errors="strict"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ModelProgramBridgeError(
            "native artifact payload cannot be reread"
        ) from exc
    if not isinstance(payload, Mapping):
        raise ModelProgramBridgeError(
            "native artifact payload root must be an object"
        )
    if hashlib.sha256(raw).hexdigest() != artifact_file_sha:
        raise ModelProgramBridgeError(
            "native artifact changed during canonical bridge"
        )

    canonical_artifact_digest = _digest(dict(payload))
    try:
        artifact = ModelArtifact(
            model_id=model_id,
            model_digest=model_digest,
            artifact_digest=canonical_artifact_digest,
            kind=loaded.receipt.schema,
            payload=dict(payload),
            training_run_id=run,
        )
    except ModelProgramError as exc:
        raise ModelProgramBridgeError(
            "native artifact violates canonical model-program contract"
        ) from exc

    spec_digest = _digest(
        {
            "schema_version": "skeleton.reverse_native_training_spec.v1",
            "run_id": run,
            "trainer_id": trainer,
            "code_revision": revision,
            "model_id": model_id,
            "model_digest": model_digest,
            "artifact_file_sha256": artifact_file_sha,
            "native_training_receipt_digest": native_receipt,
            "corpus_digest": corpus_digest,
            "hidden_size": product_receipt.get("hidden_size"),
            "seed": product_receipt.get("seed"),
            "epochs": product_receipt.get("epochs"),
            "learning_rate": product_receipt.get("learning_rate"),
            "gradient_clip": product_receipt.get("gradient_clip"),
        }
    )
    metrics = {
        "documents": _metric(
            product_receipt.get("document_count"),
            "document_count",
        ),
        "initial_loss": _metric(
            product_receipt.get("initial_loss"),
            "initial_loss",
        ),
        "final_loss": _metric(
            product_receipt.get("final_loss"),
            "final_loss",
        ),
        "epochs": _metric(
            product_receipt.get("epochs"),
            "epochs",
        ),
        "hidden_size": _metric(
            product_receipt.get("hidden_size"),
            "hidden_size",
        ),
    }
    training_receipt = TrainingReceipt(
        run_id=run,
        spec_digest=spec_digest,
        dataset_digests=(corpus_digest,),
        trainer_id=trainer,
        code_revision=revision,
        model_id=model_id,
        model_digest=model_digest,
        artifact_digest=canonical_artifact_digest,
        metrics=metrics,
    )
    source_receipt_digest = _digest(dict(product_receipt))
    bridge_payload = {
        "schema_version": "skeleton.product_model_program_bridge.v1",
        "model_id": model_id,
        "model_digest": model_digest,
        "canonical_artifact_digest": canonical_artifact_digest,
        "artifact_file_sha256": artifact_file_sha,
        "training_receipt_digest": training_receipt.digest,
        "native_training_receipt_digest": native_receipt,
        "corpus_digest": corpus_digest,
        "source_receipt_digest": source_receipt_digest,
    }
    return BridgedModelProgramArtifact(
        artifact=artifact,
        training_receipt=training_receipt,
        artifact_file_sha256=artifact_file_sha,
        native_training_receipt_digest=native_receipt,
        corpus_digest=corpus_digest,
        source_receipt_digest=source_receipt_digest,
        bridge_digest=_digest(bridge_payload),
    )


def model_promotion_receipt_from_qualification(
    bridged: BridgedModelProgramArtifact,
    qualification: LearningQualificationBundle,
    *,
    verifier_id: str,
) -> ModelPromotionReceipt:
    """Create canonical promotion evidence without activating runtime state."""

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
        != bridged.artifact_file_sha256
        or qualification.native_training_receipt_digest
        != bridged.native_training_receipt_digest
    ):
        raise ModelProgramBridgeError(
            "qualification differs from canonical bridged candidate"
        )

    verifier = _text(verifier_id, "verifier_id")
    if verifier in {
        bridged.training_receipt.trainer_id,
        qualification.mirror_verifier_id,
    }:
        raise ModelProgramBridgeError(
            "promotion verifier must be independent of trainer and Mirror verifier"
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
            "canonical promotion receipt could not be constructed"
        ) from exc


__all__ = [
    "BridgedModelProgramArtifact",
    "ModelProgramBridgeError",
    "bridge_product_training_to_model_program",
    "model_promotion_receipt_from_qualification",
]
