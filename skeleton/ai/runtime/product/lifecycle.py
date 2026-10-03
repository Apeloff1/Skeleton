"""Typed lifecycle authority for reverse-trained local AI models.

The reverse product path produces several independent pieces of evidence:
training/artifact identity, Mirror Room qualification, evaluation-firewall
holdout evidence, a canonical model-promotion receipt, and a digest-pinned local
activation manifest.  This registry is the missing state authority that orders
those receipts without collapsing their independent responsibilities.

It is intentionally non-executing.  Registering, validating, promoting,
activating, or rolling back a model here records state and evidence only; it
does not edit process environment, write activation manifests, or mutate model
weights.  Runtime selection remains an operator/deployment action.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Iterable

from skeleton.learning.model_program import ModelPromotionReceipt

from .activation import LocalModelActivationManifest
from .model_program_bridge import BridgedModelProgramArtifact
from .qualification import LearningQualificationBundle


class ModelLifecycleError(RuntimeError):
    """A model lifecycle transition is invalid or insufficiently evidenced."""


class ModelLifecycleState(str, Enum):
    CANDIDATE = "candidate"
    VALIDATED = "validated"
    PROMOTED = "promoted"
    ACTIVATED = "activated"
    ROLLED_BACK = "rolled_back"


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
        raise ModelLifecycleError(
            "model lifecycle evidence is not deterministic JSON"
        ) from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _text(value: object, name: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ModelLifecycleError(f"{name} must be non-empty text")
    result = value.strip()
    if result != value or len(result) > maximum:
        raise ModelLifecycleError(f"{name} must be normalized and bounded")
    return result


def _sha(value: object, name: str) -> str:
    result = _text(value, name, maximum=64).lower()
    if (
        len(result) != 64
        or any(ch not in "0123456789abcdef" for ch in result)
    ):
        raise ModelLifecycleError(f"{name} must be lowercase sha256")
    return result


def _refs(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ModelLifecycleError("evidence_refs must be an iterable")
    result: list[str] = []
    for raw in values:
        value = _text(raw, "evidence_ref", maximum=4096)
        if value in result:
            raise ModelLifecycleError("evidence_refs must be unique")
        result.append(value)
    if not result:
        raise ModelLifecycleError("lifecycle transition requires evidence")
    if len(result) > 256:
        raise ModelLifecycleError("lifecycle evidence exceeds hard item bound")
    return tuple(result)


@dataclass(frozen=True, slots=True)
class ModelLifecycleTransitionReceipt:
    """One append-only lifecycle state transition."""

    sequence: int
    model_id: str
    model_digest: str
    artifact_digest: str
    from_state: ModelLifecycleState | None
    to_state: ModelLifecycleState
    authority_id: str
    evidence_refs: tuple[str, ...]
    prior_transition_digest: str | None
    production_authority: bool = False
    direct_self_modify: bool = False

    def __post_init__(self) -> None:
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 1
        ):
            raise ModelLifecycleError("transition sequence must be positive")
        object.__setattr__(self, "model_id", _text(self.model_id, "model_id"))
        object.__setattr__(
            self,
            "model_digest",
            _sha(self.model_digest, "model_digest"),
        )
        object.__setattr__(
            self,
            "artifact_digest",
            _sha(self.artifact_digest, "artifact_digest"),
        )
        if self.from_state is not None:
            try:
                object.__setattr__(
                    self,
                    "from_state",
                    ModelLifecycleState(self.from_state),
                )
            except ValueError as exc:
                raise ModelLifecycleError("invalid from_state") from exc
        try:
            object.__setattr__(
                self,
                "to_state",
                ModelLifecycleState(self.to_state),
            )
        except ValueError as exc:
            raise ModelLifecycleError("invalid to_state") from exc
        object.__setattr__(
            self,
            "authority_id",
            _text(self.authority_id, "authority_id"),
        )
        object.__setattr__(self, "evidence_refs", _refs(self.evidence_refs))
        if self.prior_transition_digest is not None:
            object.__setattr__(
                self,
                "prior_transition_digest",
                _sha(
                    self.prior_transition_digest,
                    "prior_transition_digest",
                ),
            )
        if self.production_authority is not False:
            raise ModelLifecycleError(
                "lifecycle receipt cannot itself grant production authority"
            )
        if self.direct_self_modify is not False:
            raise ModelLifecycleError(
                "lifecycle receipt cannot grant direct self-modification"
            )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema_version": "skeleton.model_lifecycle_transition.v1",
                "sequence": self.sequence,
                "model_id": self.model_id,
                "model_digest": self.model_digest,
                "artifact_digest": self.artifact_digest,
                "from_state": (
                    None if self.from_state is None else self.from_state.value
                ),
                "to_state": self.to_state.value,
                "authority_id": self.authority_id,
                "evidence_refs": list(self.evidence_refs),
                "prior_transition_digest": self.prior_transition_digest,
                "production_authority": False,
                "direct_self_modify": False,
            }
        )


@dataclass(frozen=True, slots=True)
class ModelLifecycleSnapshot:
    model_id: str
    model_digest: str
    artifact_digest: str
    training_receipt_digest: str
    bridge_digest: str
    state: ModelLifecycleState
    transition_count: int
    latest_transition_digest: str
    validation_verifier_id: str | None = None
    qualification_digest: str | None = None
    promotion_verifier_id: str | None = None
    promotion_receipt_digest: str | None = None
    activation_manifest_digest: str | None = None
    rollback_model_digest: str | None = None

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema_version": "skeleton.model_lifecycle_snapshot.v1",
                "model_id": self.model_id,
                "model_digest": self.model_digest,
                "artifact_digest": self.artifact_digest,
                "training_receipt_digest": self.training_receipt_digest,
                "bridge_digest": self.bridge_digest,
                "state": self.state.value,
                "transition_count": self.transition_count,
                "latest_transition_digest": self.latest_transition_digest,
                "validation_verifier_id": self.validation_verifier_id,
                "qualification_digest": self.qualification_digest,
                "promotion_verifier_id": self.promotion_verifier_id,
                "promotion_receipt_digest": self.promotion_receipt_digest,
                "activation_manifest_digest": self.activation_manifest_digest,
                "rollback_model_digest": self.rollback_model_digest,
            }
        )


@dataclass(slots=True)
class _Record:
    bridged: BridgedModelProgramArtifact
    state: ModelLifecycleState
    history: list[ModelLifecycleTransitionReceipt]
    validation_verifier_id: str | None = None
    qualification_digest: str | None = None
    qualification_refs: tuple[str, ...] = ()
    promotion_verifier_id: str | None = None
    promotion_receipt_digest: str | None = None
    activation_manifest_digest: str | None = None
    rollback_model_digest: str | None = None


class ModelLifecycleRegistry:
    """Append-only state authority for one or more local model candidates."""

    def __init__(self) -> None:
        self._records: dict[str, _Record] = {}

    @staticmethod
    def _candidate_evidence(
        bridged: BridgedModelProgramArtifact,
    ) -> tuple[str, ...]:
        return (
            "training-receipt-sha256:" + bridged.training_receipt.digest,
            "model-program-bridge-sha256:" + bridged.bridge_digest,
            "training-plan-sha256:" + bridged.training_plan_digest,
            "learning-candidate-sha256:"
            + bridged.learning_candidate_digest,
        )

    @staticmethod
    def _next_receipt(
        record: _Record | None,
        *,
        bridged: BridgedModelProgramArtifact,
        to_state: ModelLifecycleState,
        authority_id: str,
        evidence_refs: Iterable[str],
    ) -> ModelLifecycleTransitionReceipt:
        history = () if record is None else tuple(record.history)
        return ModelLifecycleTransitionReceipt(
            sequence=len(history) + 1,
            model_id=bridged.artifact.model_id,
            model_digest=bridged.artifact.model_digest,
            artifact_digest=bridged.artifact.artifact_digest,
            from_state=None if record is None else record.state,
            to_state=to_state,
            authority_id=authority_id,
            evidence_refs=_refs(evidence_refs),
            prior_transition_digest=(
                None if not history else history[-1].digest
            ),
        )

    def register_candidate(
        self,
        bridged: BridgedModelProgramArtifact,
        *,
        authority_id: str,
    ) -> ModelLifecycleTransitionReceipt:
        if not isinstance(bridged, BridgedModelProgramArtifact):
            raise TypeError("bridged must be BridgedModelProgramArtifact")
        digest = bridged.artifact.model_digest
        prior = self._records.get(digest)
        if prior is not None:
            if prior.bridged != bridged:
                raise ModelLifecycleError(
                    "model digest is already registered with different evidence"
                )
            return prior.history[0]

        receipt = self._next_receipt(
            None,
            bridged=bridged,
            to_state=ModelLifecycleState.CANDIDATE,
            authority_id=_text(authority_id, "authority_id"),
            evidence_refs=self._candidate_evidence(bridged),
        )
        self._records[digest] = _Record(
            bridged=bridged,
            state=ModelLifecycleState.CANDIDATE,
            history=[receipt],
        )
        return receipt

    def _record(self, model_digest: str) -> _Record:
        digest = _sha(model_digest, "model_digest")
        record = self._records.get(digest)
        if record is None:
            raise ModelLifecycleError("model candidate is not registered")
        return record

    def validate(
        self,
        model_digest: str,
        qualification: LearningQualificationBundle,
        *,
        verifier_id: str,
    ) -> ModelLifecycleTransitionReceipt:
        record = self._record(model_digest)
        if record.state is not ModelLifecycleState.CANDIDATE:
            raise ModelLifecycleError(
                "validation requires candidate state"
            )
        if not isinstance(qualification, LearningQualificationBundle):
            raise TypeError(
                "qualification must be LearningQualificationBundle"
            )
        bridged = record.bridged
        if (
            qualification.candidate_model_digest
            != bridged.artifact.model_digest
            or qualification.candidate_artifact_sha256
            != bridged.artifact.artifact_digest
            or qualification.training_plan_digest
            != bridged.training_plan_digest
        ):
            raise ModelLifecycleError(
                "qualification identity differs from registered candidate"
            )
        try:
            handoff = qualification.lifecycle_validation_kwargs(
                verifier_id=verifier_id
            )
        except Exception as exc:
            raise ModelLifecycleError(
                "qualification cannot authorize lifecycle validation"
            ) from exc
        verifier = _text(handoff["verifier_id"], "validation verifier_id")
        if verifier == bridged.training_receipt.trainer_id:
            raise ModelLifecycleError(
                "training authority cannot validate its own candidate"
            )
        refs = (
            *qualification.lifecycle_evidence_refs,
            "learning-qualification-sha256:"
            + qualification.qualification_digest,
        )
        receipt = self._next_receipt(
            record,
            bridged=bridged,
            to_state=ModelLifecycleState.VALIDATED,
            authority_id=verifier,
            evidence_refs=refs,
        )
        record.state = ModelLifecycleState.VALIDATED
        record.validation_verifier_id = verifier
        record.qualification_digest = qualification.qualification_digest
        record.qualification_refs = tuple(qualification.lifecycle_evidence_refs)
        record.history.append(receipt)
        return receipt

    def promote(
        self,
        model_digest: str,
        promotion_receipt: ModelPromotionReceipt,
    ) -> ModelLifecycleTransitionReceipt:
        record = self._record(model_digest)
        if record.state is not ModelLifecycleState.VALIDATED:
            raise ModelLifecycleError(
                "promotion requires validated state"
            )
        if not isinstance(promotion_receipt, ModelPromotionReceipt):
            raise TypeError(
                "promotion_receipt must be ModelPromotionReceipt"
            )
        bridged = record.bridged
        if (
            promotion_receipt.model_id != bridged.artifact.model_id
            or promotion_receipt.model_digest != bridged.artifact.model_digest
            or promotion_receipt.training_receipt_digest
            != bridged.training_receipt.digest
        ):
            raise ModelLifecycleError(
                "promotion receipt identity differs from validated candidate"
            )
        verifier = _text(
            promotion_receipt.verifier_id,
            "promotion verifier_id",
        )
        forbidden = {
            bridged.training_receipt.trainer_id,
            record.validation_verifier_id,
        }
        if verifier in forbidden:
            raise ModelLifecycleError(
                "promotion verifier must be independent of trainer and lifecycle validator"
            )
        required_refs = {
            *record.qualification_refs,
            "learning-qualification-sha256:"
            + _sha(record.qualification_digest, "qualification_digest"),
            "model-program-bridge-sha256:" + bridged.bridge_digest,
        }
        if not required_refs.issubset(
            set(promotion_receipt.evaluation_refs)
        ):
            raise ModelLifecycleError(
                "promotion receipt lacks validated lifecycle evidence"
            )

        receipt = self._next_receipt(
            record,
            bridged=bridged,
            to_state=ModelLifecycleState.PROMOTED,
            authority_id=verifier,
            evidence_refs=(
                "model-promotion-receipt-sha256:"
                + promotion_receipt.digest,
                *promotion_receipt.evaluation_refs,
            ),
        )
        record.state = ModelLifecycleState.PROMOTED
        record.promotion_verifier_id = verifier
        record.promotion_receipt_digest = promotion_receipt.digest
        record.history.append(receipt)
        return receipt

    def activate(
        self,
        model_digest: str,
        manifest: LocalModelActivationManifest,
        *,
        deployment_authority_id: str,
    ) -> ModelLifecycleTransitionReceipt:
        record = self._record(model_digest)
        if record.state is not ModelLifecycleState.PROMOTED:
            raise ModelLifecycleError(
                "activation requires promoted state"
            )
        if not isinstance(manifest, LocalModelActivationManifest):
            raise TypeError(
                "manifest must be LocalModelActivationManifest"
            )
        bridged = record.bridged
        if (
            manifest.candidate_model_id != bridged.artifact.model_id
            or manifest.candidate_model_digest
            != bridged.artifact.model_digest
            or manifest.candidate_artifact_sha256
            != bridged.artifact.artifact_digest
        ):
            raise ModelLifecycleError(
                "activation manifest candidate identity drift"
            )
        if (
            record.promotion_receipt_digest is None
            or manifest.promotion_receipt_digest
            != record.promotion_receipt_digest
        ):
            raise ModelLifecycleError(
                "activation manifest promotion identity drift"
            )
        if (
            record.qualification_digest is None
            or manifest.qualification_digest
            != record.qualification_digest
        ):
            raise ModelLifecycleError(
                "activation manifest qualification identity drift"
            )
        if manifest.model_program_bridge_digest != bridged.bridge_digest:
            raise ModelLifecycleError(
                "activation manifest bridge identity drift"
            )
        if manifest.direct_self_modify is not False:
            raise ModelLifecycleError(
                "activation cannot grant direct self-modification"
            )
        authority = _text(
            deployment_authority_id,
            "deployment_authority_id",
        )
        forbidden = {
            bridged.training_receipt.trainer_id,
            record.validation_verifier_id,
            record.promotion_verifier_id,
        }
        if authority in forbidden:
            raise ModelLifecycleError(
                "deployment authority must be independent of training and verification"
            )

        receipt = self._next_receipt(
            record,
            bridged=bridged,
            to_state=ModelLifecycleState.ACTIVATED,
            authority_id=authority,
            evidence_refs=(
                "activation-manifest-sha256:" + manifest.manifest_digest,
                "operator-authorization:"
                + manifest.operator_authorization_ref,
                "rollback-model-sha256:" + manifest.baseline_model_digest,
                "rollback-artifact-sha256:"
                + manifest.baseline_artifact_sha256,
            ),
        )
        record.state = ModelLifecycleState.ACTIVATED
        record.activation_manifest_digest = manifest.manifest_digest
        record.rollback_model_digest = manifest.baseline_model_digest
        record.history.append(receipt)
        return receipt

    def rollback(
        self,
        model_digest: str,
        manifest: LocalModelActivationManifest,
        *,
        deployment_authority_id: str,
    ) -> ModelLifecycleTransitionReceipt:
        record = self._record(model_digest)
        if record.state is not ModelLifecycleState.ACTIVATED:
            raise ModelLifecycleError(
                "rollback requires activated state"
            )
        if not isinstance(manifest, LocalModelActivationManifest):
            raise TypeError(
                "manifest must be LocalModelActivationManifest"
            )
        if (
            record.activation_manifest_digest is None
            or manifest.manifest_digest
            != record.activation_manifest_digest
        ):
            raise ModelLifecycleError(
                "rollback requires the exact activated manifest"
            )
        if (
            record.rollback_model_digest is None
            or manifest.baseline_model_digest
            != record.rollback_model_digest
        ):
            raise ModelLifecycleError(
                "rollback baseline identity drift"
            )
        authority = _text(
            deployment_authority_id,
            "deployment_authority_id",
        )
        forbidden = {
            record.bridged.training_receipt.trainer_id,
            record.validation_verifier_id,
            record.promotion_verifier_id,
        }
        if authority in forbidden:
            raise ModelLifecycleError(
                "rollback authority must be independent of training and verification"
            )
        receipt = self._next_receipt(
            record,
            bridged=record.bridged,
            to_state=ModelLifecycleState.ROLLED_BACK,
            authority_id=authority,
            evidence_refs=(
                "activation-manifest-sha256:" + manifest.manifest_digest,
                "rollback-model-sha256:" + manifest.baseline_model_digest,
                "rollback-artifact-sha256:"
                + manifest.baseline_artifact_sha256,
            ),
        )
        record.state = ModelLifecycleState.ROLLED_BACK
        record.history.append(receipt)
        return receipt

    def history(
        self,
        model_digest: str,
    ) -> tuple[ModelLifecycleTransitionReceipt, ...]:
        return tuple(self._record(model_digest).history)

    def snapshot(self, model_digest: str) -> ModelLifecycleSnapshot:
        record = self._record(model_digest)
        latest = record.history[-1]
        bridged = record.bridged
        return ModelLifecycleSnapshot(
            model_id=bridged.artifact.model_id,
            model_digest=bridged.artifact.model_digest,
            artifact_digest=bridged.artifact.artifact_digest,
            training_receipt_digest=bridged.training_receipt.digest,
            bridge_digest=bridged.bridge_digest,
            state=record.state,
            transition_count=len(record.history),
            latest_transition_digest=latest.digest,
            validation_verifier_id=record.validation_verifier_id,
            qualification_digest=record.qualification_digest,
            promotion_verifier_id=record.promotion_verifier_id,
            promotion_receipt_digest=record.promotion_receipt_digest,
            activation_manifest_digest=record.activation_manifest_digest,
            rollback_model_digest=record.rollback_model_digest,
        )

    def verify_history(self, model_digest: str) -> bool:
        history = self.history(model_digest)
        prior: str | None = None
        expected_sequence = 1
        expected_from: ModelLifecycleState | None = None
        for receipt in history:
            if receipt.sequence != expected_sequence:
                raise ModelLifecycleError(
                    "lifecycle transition sequence is not contiguous"
                )
            if receipt.prior_transition_digest != prior:
                raise ModelLifecycleError(
                    "lifecycle transition digest chain is broken"
                )
            if receipt.from_state != expected_from:
                raise ModelLifecycleError(
                    "lifecycle transition state chain is broken"
                )
            prior = receipt.digest
            expected_from = receipt.to_state
            expected_sequence += 1
        return True


__all__ = [
    "ModelLifecycleError",
    "ModelLifecycleRegistry",
    "ModelLifecycleSnapshot",
    "ModelLifecycleState",
    "ModelLifecycleTransitionReceipt",
]
