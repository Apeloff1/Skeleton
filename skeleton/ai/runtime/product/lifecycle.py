"""Durable typed lifecycle authority for reverse-trained local AI models.

The reverse product path produces independent training, evaluation, promotion,
and activation evidence. This registry orders those authorities without
collapsing them and can atomically persist only the compact identities needed
to resume lifecycle decisions after restart.

The registry is deliberately non-executing. It cannot train weights, write an
activation manifest, edit process environment, or select the runtime target.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable, Mapping

from skeleton.learning.model_program import ModelPromotionReceipt

from .activation import LocalModelActivationManifest
from .model_program_bridge import BridgedModelProgramArtifact
from .qualification import LearningQualificationBundle


_STATE_SCHEMA = "skeleton.model_lifecycle_registry.v1"
_MAX_STATE_BYTES = 8 * 1024 * 1024
_MAX_RECORDS = 10_000
_MAX_EVIDENCE_REFS = 256


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


def _optional_text(value: object, name: str) -> str | None:
    if value is None:
        return None
    return _text(value, name)


def _optional_sha(value: object, name: str) -> str | None:
    if value is None:
        return None
    return _sha(value, name)


def _refs(
    values: Iterable[str],
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ModelLifecycleError("evidence_refs must be an iterable")
    result: list[str] = []
    for raw in values:
        value = _text(raw, "evidence_ref", maximum=4096)
        if value in result:
            raise ModelLifecycleError("evidence_refs must be unique")
        result.append(value)
    if not result and not allow_empty:
        raise ModelLifecycleError("lifecycle transition requires evidence")
    if len(result) > _MAX_EVIDENCE_REFS:
        raise ModelLifecycleError("lifecycle evidence exceeds hard item bound")
    return tuple(result)


def _strict_object(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ModelLifecycleError(
                f"lifecycle state contains duplicate key: {key}"
            )
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ModelLifecycleError(
        "lifecycle state contains non-finite constant: " + value
    )


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
        return _digest(self.as_dict())

    def as_dict(self) -> dict[str, object]:
        return {
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

    @classmethod
    def from_dict(
        cls,
        value: Mapping[str, object],
    ) -> "ModelLifecycleTransitionReceipt":
        if not isinstance(value, Mapping):
            raise ModelLifecycleError("lifecycle transition must be an object")
        allowed = {
            "schema_version",
            "sequence",
            "model_id",
            "model_digest",
            "artifact_digest",
            "from_state",
            "to_state",
            "authority_id",
            "evidence_refs",
            "prior_transition_digest",
            "production_authority",
            "direct_self_modify",
        }
        if set(value) != allowed:
            raise ModelLifecycleError(
                "lifecycle transition field set mismatch"
            )
        if value.get("schema_version") != (
            "skeleton.model_lifecycle_transition.v1"
        ):
            raise ModelLifecycleError(
                "unsupported lifecycle transition schema"
            )
        evidence = value.get("evidence_refs")
        if not isinstance(evidence, list):
            raise ModelLifecycleError(
                "lifecycle transition evidence_refs must be a list"
            )
        return cls(
            sequence=value["sequence"],  # type: ignore[arg-type]
            model_id=value["model_id"],  # type: ignore[arg-type]
            model_digest=value["model_digest"],  # type: ignore[arg-type]
            artifact_digest=value["artifact_digest"],  # type: ignore[arg-type]
            from_state=value["from_state"],  # type: ignore[arg-type]
            to_state=value["to_state"],  # type: ignore[arg-type]
            authority_id=value["authority_id"],  # type: ignore[arg-type]
            evidence_refs=tuple(evidence),  # type: ignore[arg-type]
            prior_transition_digest=value[
                "prior_transition_digest"
            ],  # type: ignore[arg-type]
            production_authority=value[
                "production_authority"
            ],  # type: ignore[arg-type]
            direct_self_modify=value[
                "direct_self_modify"
            ],  # type: ignore[arg-type]
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
    promotion_transition_digest: str | None = None
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
                "promotion_transition_digest": self.promotion_transition_digest,
                "activation_manifest_digest": self.activation_manifest_digest,
                "rollback_model_digest": self.rollback_model_digest,
            }
        )


@dataclass(slots=True)
class _Record:
    model_id: str
    model_digest: str
    artifact_digest: str
    training_receipt_digest: str
    trainer_id: str
    bridge_digest: str
    training_plan_digest: str
    learning_candidate_digest: str
    state: ModelLifecycleState
    history: list[ModelLifecycleTransitionReceipt]
    validation_verifier_id: str | None = None
    qualification_digest: str | None = None
    qualification_refs: tuple[str, ...] = ()
    promotion_verifier_id: str | None = None
    promotion_receipt_digest: str | None = None
    promotion_transition_digest: str | None = None
    activation_manifest_digest: str | None = None
    rollback_model_digest: str | None = None

    @classmethod
    def from_bridged(
        cls,
        bridged: BridgedModelProgramArtifact,
        receipt: ModelLifecycleTransitionReceipt,
    ) -> "_Record":
        return cls(
            model_id=bridged.artifact.model_id,
            model_digest=bridged.artifact.model_digest,
            artifact_digest=bridged.artifact.artifact_digest,
            training_receipt_digest=bridged.training_receipt.digest,
            trainer_id=bridged.training_receipt.trainer_id,
            bridge_digest=bridged.bridge_digest,
            training_plan_digest=bridged.training_plan_digest,
            learning_candidate_digest=bridged.learning_candidate_digest,
            state=ModelLifecycleState.CANDIDATE,
            history=[receipt],
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "model_digest": self.model_digest,
            "artifact_digest": self.artifact_digest,
            "training_receipt_digest": self.training_receipt_digest,
            "trainer_id": self.trainer_id,
            "bridge_digest": self.bridge_digest,
            "training_plan_digest": self.training_plan_digest,
            "learning_candidate_digest": self.learning_candidate_digest,
            "state": self.state.value,
            "history": [item.as_dict() for item in self.history],
            "validation_verifier_id": self.validation_verifier_id,
            "qualification_digest": self.qualification_digest,
            "qualification_refs": list(self.qualification_refs),
            "promotion_verifier_id": self.promotion_verifier_id,
            "promotion_receipt_digest": self.promotion_receipt_digest,
            "promotion_transition_digest": self.promotion_transition_digest,
            "activation_manifest_digest": self.activation_manifest_digest,
            "rollback_model_digest": self.rollback_model_digest,
        }


class ModelLifecycleRegistry:
    """Append-only lifecycle authority with optional atomic durable state."""

    def __init__(
        self,
        state_path: str | Path | None = None,
    ) -> None:
        self._records: dict[str, _Record] = {}
        self._state_path = self._normalize_state_path(state_path)
        if self._state_path is not None and self._state_path.exists():
            self._load()

    @staticmethod
    def _normalize_state_path(
        value: str | Path | None,
    ) -> Path | None:
        if value is None:
            return None
        raw = str(value).strip()
        if not raw:
            raise ModelLifecycleError(
                "lifecycle state path must be non-empty"
            )
        path = Path(raw).expanduser()
        if path.is_symlink():
            raise ModelLifecycleError(
                "lifecycle state path symlink is forbidden"
            )
        try:
            parent = path.parent.resolve(strict=True)
        except OSError as exc:
            raise ModelLifecycleError(
                "lifecycle state parent is unavailable"
            ) from exc
        if not parent.is_dir():
            raise ModelLifecycleError(
                "lifecycle state parent must be a directory"
            )
        return parent / path.name

    @property
    def state_path(self) -> Path | None:
        return self._state_path

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
        model_id: str,
        model_digest: str,
        artifact_digest: str,
        to_state: ModelLifecycleState,
        authority_id: str,
        evidence_refs: Iterable[str],
    ) -> ModelLifecycleTransitionReceipt:
        history = () if record is None else tuple(record.history)
        return ModelLifecycleTransitionReceipt(
            sequence=len(history) + 1,
            model_id=model_id,
            model_digest=model_digest,
            artifact_digest=artifact_digest,
            from_state=None if record is None else record.state,
            to_state=to_state,
            authority_id=authority_id,
            evidence_refs=_refs(evidence_refs),
            prior_transition_digest=(
                None if not history else history[-1].digest
            ),
        )

    def _record(self, model_digest: str) -> _Record:
        digest = _sha(model_digest, "model_digest")
        record = self._records.get(digest)
        if record is None:
            raise ModelLifecycleError("model candidate is not registered")
        return record

    @staticmethod
    def _same_bridged_identity(
        record: _Record,
        bridged: BridgedModelProgramArtifact,
    ) -> bool:
        return (
            record.model_id == bridged.artifact.model_id
            and record.model_digest == bridged.artifact.model_digest
            and record.artifact_digest == bridged.artifact.artifact_digest
            and record.training_receipt_digest
            == bridged.training_receipt.digest
            and record.trainer_id == bridged.training_receipt.trainer_id
            and record.bridge_digest == bridged.bridge_digest
            and record.training_plan_digest
            == bridged.training_plan_digest
            and record.learning_candidate_digest
            == bridged.learning_candidate_digest
        )

    def _commit_record(
        self,
        model_digest: str,
        staged: _Record,
        *,
        prior: _Record | None,
    ) -> None:
        """Publish one staged lifecycle record only if durable persistence succeeds.

        Lifecycle decisions are fail-closed across the process/disk boundary:
        callers never observe a state transition in memory when the canonical
        state file could not be atomically committed.
        """

        self._records[model_digest] = staged
        try:
            self._persist()
        except ModelLifecycleError:
            if prior is None:
                self._records.pop(model_digest, None)
            else:
                self._records[model_digest] = prior
            raise

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
            if not self._same_bridged_identity(prior, bridged):
                raise ModelLifecycleError(
                    "model digest is already registered with different evidence"
                )
            return prior.history[0]

        receipt = self._next_receipt(
            None,
            model_id=bridged.artifact.model_id,
            model_digest=bridged.artifact.model_digest,
            artifact_digest=bridged.artifact.artifact_digest,
            to_state=ModelLifecycleState.CANDIDATE,
            authority_id=_text(authority_id, "authority_id"),
            evidence_refs=self._candidate_evidence(bridged),
        )
        staged = _Record.from_bridged(bridged, receipt)
        self._commit_record(digest, staged, prior=None)
        return receipt

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
        if (
            qualification.candidate_model_digest != record.model_digest
            or qualification.candidate_artifact_sha256
            != record.artifact_digest
            or qualification.training_plan_digest
            != record.training_plan_digest
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
        if verifier == record.trainer_id:
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
            model_id=record.model_id,
            model_digest=record.model_digest,
            artifact_digest=record.artifact_digest,
            to_state=ModelLifecycleState.VALIDATED,
            authority_id=verifier,
            evidence_refs=refs,
        )
        staged = replace(
            record,
            state=ModelLifecycleState.VALIDATED,
            history=[*record.history, receipt],
            validation_verifier_id=verifier,
            qualification_digest=qualification.qualification_digest,
            qualification_refs=tuple(
                qualification.lifecycle_evidence_refs
            ),
        )
        self._commit_record(record.model_digest, staged, prior=record)
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
        if (
            promotion_receipt.model_id != record.model_id
            or promotion_receipt.model_digest != record.model_digest
            or promotion_receipt.training_receipt_digest
            != record.training_receipt_digest
        ):
            raise ModelLifecycleError(
                "promotion receipt identity differs from validated candidate"
            )
        verifier = _text(
            promotion_receipt.verifier_id,
            "promotion verifier_id",
        )
        forbidden = {
            record.trainer_id,
            record.validation_verifier_id,
        }
        if verifier in forbidden:
            raise ModelLifecycleError(
                "promotion verifier must be independent of trainer and lifecycle validator"
            )
        qualification_digest = _sha(
            record.qualification_digest,
            "qualification_digest",
        )
        required_refs = {
            *record.qualification_refs,
            "learning-qualification-sha256:" + qualification_digest,
            "model-program-bridge-sha256:" + record.bridge_digest,
        }
        if not required_refs.issubset(
            set(promotion_receipt.evaluation_refs)
        ):
            raise ModelLifecycleError(
                "promotion receipt lacks validated lifecycle evidence"
            )

        receipt = self._next_receipt(
            record,
            model_id=record.model_id,
            model_digest=record.model_digest,
            artifact_digest=record.artifact_digest,
            to_state=ModelLifecycleState.PROMOTED,
            authority_id=verifier,
            evidence_refs=(
                "model-promotion-receipt-sha256:"
                + promotion_receipt.digest,
                *promotion_receipt.evaluation_refs,
            ),
        )
        staged = replace(
            record,
            state=ModelLifecycleState.PROMOTED,
            history=[*record.history, receipt],
            promotion_verifier_id=verifier,
            promotion_receipt_digest=promotion_receipt.digest,
            promotion_transition_digest=receipt.digest,
        )
        self._commit_record(record.model_digest, staged, prior=record)
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
        if (
            manifest.candidate_model_id != record.model_id
            or manifest.candidate_model_digest != record.model_digest
            or manifest.candidate_artifact_sha256
            != record.artifact_digest
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
            record.promotion_transition_digest is None
            or manifest.lifecycle_promotion_transition_digest
            != record.promotion_transition_digest
        ):
            raise ModelLifecycleError(
                "activation manifest lifecycle promotion transition drift"
            )
        if (
            record.qualification_digest is None
            or manifest.qualification_digest
            != record.qualification_digest
        ):
            raise ModelLifecycleError(
                "activation manifest qualification identity drift"
            )
        if manifest.model_program_bridge_digest != record.bridge_digest:
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
            record.trainer_id,
            record.validation_verifier_id,
            record.promotion_verifier_id,
        }
        if authority in forbidden:
            raise ModelLifecycleError(
                "deployment authority must be independent of training and verification"
            )

        receipt = self._next_receipt(
            record,
            model_id=record.model_id,
            model_digest=record.model_digest,
            artifact_digest=record.artifact_digest,
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
        staged = replace(
            record,
            state=ModelLifecycleState.ACTIVATED,
            history=[*record.history, receipt],
            activation_manifest_digest=manifest.manifest_digest,
            rollback_model_digest=manifest.baseline_model_digest,
        )
        self._commit_record(record.model_digest, staged, prior=record)
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
            record.trainer_id,
            record.validation_verifier_id,
            record.promotion_verifier_id,
        }
        if authority in forbidden:
            raise ModelLifecycleError(
                "rollback authority must be independent of training and verification"
            )
        receipt = self._next_receipt(
            record,
            model_id=record.model_id,
            model_digest=record.model_digest,
            artifact_digest=record.artifact_digest,
            to_state=ModelLifecycleState.ROLLED_BACK,
            authority_id=authority,
            evidence_refs=(
                "activation-manifest-sha256:" + manifest.manifest_digest,
                "rollback-model-sha256:" + manifest.baseline_model_digest,
                "rollback-artifact-sha256:"
                + manifest.baseline_artifact_sha256,
            ),
        )
        staged = replace(
            record,
            state=ModelLifecycleState.ROLLED_BACK,
            history=[*record.history, receipt],
        )
        self._commit_record(record.model_digest, staged, prior=record)
        return receipt

    def history(
        self,
        model_digest: str,
    ) -> tuple[ModelLifecycleTransitionReceipt, ...]:
        return tuple(self._record(model_digest).history)

    def snapshot(self, model_digest: str) -> ModelLifecycleSnapshot:
        record = self._record(model_digest)
        latest = record.history[-1]
        return ModelLifecycleSnapshot(
            model_id=record.model_id,
            model_digest=record.model_digest,
            artifact_digest=record.artifact_digest,
            training_receipt_digest=record.training_receipt_digest,
            bridge_digest=record.bridge_digest,
            state=record.state,
            transition_count=len(record.history),
            latest_transition_digest=latest.digest,
            validation_verifier_id=record.validation_verifier_id,
            qualification_digest=record.qualification_digest,
            promotion_verifier_id=record.promotion_verifier_id,
            promotion_receipt_digest=record.promotion_receipt_digest,
            promotion_transition_digest=record.promotion_transition_digest,
            activation_manifest_digest=record.activation_manifest_digest,
            rollback_model_digest=record.rollback_model_digest,
        )

    def verify_history(self, model_digest: str) -> bool:
        self._verify_record_history(self._record(model_digest))
        return True

    @staticmethod
    def _verify_record_history(record: _Record) -> None:
        if not record.history:
            raise ModelLifecycleError(
                "lifecycle record must contain transition history"
            )
        prior: str | None = None
        expected_from: ModelLifecycleState | None = None
        for expected_sequence, receipt in enumerate(
            record.history,
            start=1,
        ):
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
            if (
                receipt.model_id != record.model_id
                or receipt.model_digest != record.model_digest
                or receipt.artifact_digest != record.artifact_digest
            ):
                raise ModelLifecycleError(
                    "lifecycle transition model identity drift"
                )
            prior = receipt.digest
            expected_from = receipt.to_state
        if record.history[-1].to_state is not record.state:
            raise ModelLifecycleError(
                "lifecycle record state differs from transition history"
            )

    def _state_payload(self) -> dict[str, object]:
        records = [
            self._records[key].as_dict()
            for key in sorted(self._records)
        ]
        return {
            "schema_version": _STATE_SCHEMA,
            "records": records,
        }

    def state_digest(self) -> str:
        return _digest(self._state_payload())

    def _persist(self) -> None:
        path = self._state_path
        if path is None:
            return
        if path.is_symlink():
            raise ModelLifecycleError(
                "lifecycle state path symlink is forbidden"
            )
        payload = self._state_payload()
        envelope = {
            **payload,
            "state_digest": _digest(payload),
        }
        raw = (_stable_json(envelope) + "\n").encode("utf-8")
        if len(raw) > _MAX_STATE_BYTES:
            raise ModelLifecycleError(
                "lifecycle state exceeds hard byte limit"
            )

        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=path.name + ".",
                suffix=".tmp",
                dir=str(path.parent),
                delete=False,
            ) as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
                temp_path = Path(handle.name)
            os.chmod(temp_path, 0o600)
            os.replace(temp_path, path)
            temp_path = None
            try:
                directory_fd = os.open(str(path.parent), os.O_RDONLY)
            except OSError:
                directory_fd = None
            if directory_fd is not None:
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        except OSError as exc:
            raise ModelLifecycleError(
                "lifecycle state could not be written atomically"
            ) from exc
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass

    @staticmethod
    def _record_from_dict(value: Mapping[str, object]) -> _Record:
        if not isinstance(value, Mapping):
            raise ModelLifecycleError("lifecycle record must be an object")
        allowed = {
            "model_id",
            "model_digest",
            "artifact_digest",
            "training_receipt_digest",
            "trainer_id",
            "bridge_digest",
            "training_plan_digest",
            "learning_candidate_digest",
            "state",
            "history",
            "validation_verifier_id",
            "qualification_digest",
            "qualification_refs",
            "promotion_verifier_id",
            "promotion_receipt_digest",
            "promotion_transition_digest",
            "activation_manifest_digest",
            "rollback_model_digest",
        }
        if set(value) != allowed:
            raise ModelLifecycleError("lifecycle record field set mismatch")
        try:
            state = ModelLifecycleState(value["state"])
        except (ValueError, TypeError) as exc:
            raise ModelLifecycleError(
                "lifecycle record has invalid state"
            ) from exc
        raw_history = value.get("history")
        if not isinstance(raw_history, list):
            raise ModelLifecycleError(
                "lifecycle record history must be a list"
            )
        raw_refs = value.get("qualification_refs")
        if not isinstance(raw_refs, list):
            raise ModelLifecycleError(
                "qualification_refs must be a list"
            )
        record = _Record(
            model_id=_text(value["model_id"], "model_id"),
            model_digest=_sha(value["model_digest"], "model_digest"),
            artifact_digest=_sha(
                value["artifact_digest"],
                "artifact_digest",
            ),
            training_receipt_digest=_sha(
                value["training_receipt_digest"],
                "training_receipt_digest",
            ),
            trainer_id=_text(value["trainer_id"], "trainer_id"),
            bridge_digest=_sha(value["bridge_digest"], "bridge_digest"),
            training_plan_digest=_sha(
                value["training_plan_digest"],
                "training_plan_digest",
            ),
            learning_candidate_digest=_sha(
                value["learning_candidate_digest"],
                "learning_candidate_digest",
            ),
            state=state,
            history=[
                ModelLifecycleTransitionReceipt.from_dict(item)
                for item in raw_history
            ],
            validation_verifier_id=_optional_text(
                value.get("validation_verifier_id"),
                "validation_verifier_id",
            ),
            qualification_digest=_optional_sha(
                value.get("qualification_digest"),
                "qualification_digest",
            ),
            qualification_refs=_refs(
                raw_refs,  # type: ignore[arg-type]
                allow_empty=True,
            ),
            promotion_verifier_id=_optional_text(
                value.get("promotion_verifier_id"),
                "promotion_verifier_id",
            ),
            promotion_receipt_digest=_optional_sha(
                value.get("promotion_receipt_digest"),
                "promotion_receipt_digest",
            ),
            promotion_transition_digest=_optional_sha(
                value.get("promotion_transition_digest"),
                "promotion_transition_digest",
            ),
            activation_manifest_digest=_optional_sha(
                value.get("activation_manifest_digest"),
                "activation_manifest_digest",
            ),
            rollback_model_digest=_optional_sha(
                value.get("rollback_model_digest"),
                "rollback_model_digest",
            ),
        )
        ModelLifecycleRegistry._verify_record_history(record)

        if state is not ModelLifecycleState.CANDIDATE:
            if (
                record.validation_verifier_id is None
                or record.qualification_digest is None
                or not record.qualification_refs
            ):
                raise ModelLifecycleError(
                    "validated lifecycle state lacks qualification identity"
                )
        if state in {
            ModelLifecycleState.PROMOTED,
            ModelLifecycleState.ACTIVATED,
            ModelLifecycleState.ROLLED_BACK,
        }:
            if (
                record.promotion_verifier_id is None
                or record.promotion_receipt_digest is None
                or record.promotion_transition_digest is None
            ):
                raise ModelLifecycleError(
                    "promoted lifecycle state lacks promotion identity"
                )
        if state in {
            ModelLifecycleState.ACTIVATED,
            ModelLifecycleState.ROLLED_BACK,
        }:
            if (
                record.activation_manifest_digest is None
                or record.rollback_model_digest is None
            ):
                raise ModelLifecycleError(
                    "activated lifecycle state lacks rollback identity"
                )
        return record

    def _load(self) -> None:
        path = self._state_path
        assert path is not None
        if path.is_symlink():
            raise ModelLifecycleError(
                "lifecycle state path symlink is forbidden"
            )
        try:
            resolved = path.resolve(strict=True)
            stat = resolved.stat()
            raw = resolved.read_bytes()
        except OSError as exc:
            raise ModelLifecycleError(
                "lifecycle state is unavailable"
            ) from exc
        if not resolved.is_file():
            raise ModelLifecycleError(
                "lifecycle state must be a regular file"
            )
        if (
            stat.st_size < 1
            or stat.st_size > _MAX_STATE_BYTES
            or len(raw) != stat.st_size
        ):
            raise ModelLifecycleError(
                "lifecycle state byte bounds/identity failed"
            )
        try:
            payload = json.loads(
                raw.decode("utf-8", errors="strict"),
                object_pairs_hook=_strict_object,
                parse_constant=_reject_constant,
            )
        except UnicodeDecodeError as exc:
            raise ModelLifecycleError(
                "lifecycle state must be UTF-8 JSON"
            ) from exc
        except json.JSONDecodeError as exc:
            raise ModelLifecycleError(
                "lifecycle state contains invalid JSON"
            ) from exc
        if not isinstance(payload, Mapping):
            raise ModelLifecycleError(
                "lifecycle state root must be an object"
            )
        if set(payload) != {
            "schema_version",
            "records",
            "state_digest",
        }:
            raise ModelLifecycleError(
                "lifecycle state field set mismatch"
            )
        if payload.get("schema_version") != _STATE_SCHEMA:
            raise ModelLifecycleError(
                "unsupported lifecycle state schema"
            )
        records = payload.get("records")
        if not isinstance(records, list):
            raise ModelLifecycleError(
                "lifecycle state records must be a list"
            )
        if len(records) > _MAX_RECORDS:
            raise ModelLifecycleError(
                "lifecycle state exceeds record bound"
            )
        expected = _sha(
            payload.get("state_digest"),
            "state_digest",
        )
        unsigned = {
            "schema_version": payload["schema_version"],
            "records": records,
        }
        if _digest(unsigned) != expected:
            raise ModelLifecycleError(
                "lifecycle state digest mismatch"
            )

        restored: dict[str, _Record] = {}
        for raw_record in records:
            record = self._record_from_dict(raw_record)
            if record.model_digest in restored:
                raise ModelLifecycleError(
                    "lifecycle state contains duplicate model identity"
                )
            restored[record.model_digest] = record
        self._records = restored


__all__ = [
    "ModelLifecycleError",
    "ModelLifecycleRegistry",
    "ModelLifecycleSnapshot",
    "ModelLifecycleState",
    "ModelLifecycleTransitionReceipt",
]
