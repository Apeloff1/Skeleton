"""Post-operation proof for destructive durable evidence compaction.

This module binds the independently-authorized pieces of one completed
compaction workflow into a single signed audit artifact.  The proof is
intentionally non-authorizing: it can demonstrate that a destructive operation
was coherent after the fact, but it can never grant authority to prune data.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import time
from typing import Callable

from skeleton.shells.ai.durable_archive import (
    DurableArchiveVerification,
    SignedDurableArchiveManifest,
)
from skeleton.shells.ai.durable_compaction_certificate import (
    SignedDurableCompactionCertificate,
)
from skeleton.shells.ai.durable_compaction_operator import (
    DurableCompactionWorkflow,
)
from skeleton.shells.ai.durable_compaction_reservation import (
    SignedDurableCompactionReservation,
)
from skeleton.shells.ai.durable_pruning import DurablePruningResult
from skeleton.shells.ai.durable_pruning_authorization import (
    SignedDurablePruningAuthorization,
)
from skeleton.shells.ai.signed_artifact import (
    ArtifactSignatureError,
    ArtifactSigner,
    SignedArtifact,
)


def _digest(name: str, value: str) -> str:
    if len(value) != 64:
        raise ValueError(f"{name} must be SHA-256 hex")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{name} must be SHA-256 hex") from exc
    return value.lower()


def _identity(name: str, value: str, *, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
    ):
        raise ValueError(f"invalid {name}")
    return value


@dataclass(frozen=True)
class DurableCompactionProof:
    schema_version: int
    proof_id: str
    workflow_id: str
    workflow_digest: str
    chain_id: str
    operator_id: str
    reservation_id: str
    reservation_digest: str
    reservation_generation: int
    certificate_id: str
    certificate_digest: str
    authorization_id: str
    authorization_digest: str
    archive_id: str
    archive_manifest_digest: str
    pruning_operation_id: str
    pruning_manifest_digest: str
    floor_id: str
    floor_digest: str
    current_sequence: int
    current_root: str
    cutoff_sequence: int
    cutoff_root: str
    previous_floor_sequence: int
    previous_floor_root: str
    delete_count: int
    deleted_items: int
    fencing_token: int
    archive_verification_digest: str
    completed_at: float
    issued_at: float

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(
                "unsupported durable compaction proof schema"
            )
        for name in (
            "proof_id",
            "workflow_id",
            "workflow_digest",
            "reservation_id",
            "reservation_digest",
            "certificate_id",
            "certificate_digest",
            "authorization_id",
            "authorization_digest",
            "archive_manifest_digest",
            "pruning_operation_id",
            "pruning_manifest_digest",
            "floor_id",
            "floor_digest",
            "current_root",
            "cutoff_root",
            "previous_floor_root",
            "archive_verification_digest",
        ):
            object.__setattr__(
                self,
                name,
                _digest(name, getattr(self, name)),
            )
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        _identity(
            "operator_id",
            self.operator_id,
            maximum=256,
        )
        _identity(
            "archive_id",
            self.archive_id,
            maximum=256,
        )
        for name in (
            "reservation_generation",
            "current_sequence",
            "cutoff_sequence",
            "delete_count",
            "deleted_items",
            "fencing_token",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise ValueError(
                    f"{name} must be positive integer"
                )
        if (
            isinstance(self.previous_floor_sequence, bool)
            or not isinstance(self.previous_floor_sequence, int)
            or self.previous_floor_sequence < 0
        ):
            raise ValueError(
                "previous_floor_sequence must be non-negative integer"
            )
        if self.cutoff_sequence > self.current_sequence:
            raise ValueError(
                "proof cutoff exceeds original chain head"
            )
        if self.previous_floor_sequence >= self.cutoff_sequence:
            raise ValueError(
                "proof cutoff must advance previous floor"
            )
        if self.delete_count != (
            self.cutoff_sequence
            - self.previous_floor_sequence
        ):
            raise ValueError(
                "proof delete_count differs from floor interval"
            )
        if self.deleted_items != self.delete_count:
            raise ValueError(
                "completed proof requires all planned items deleted"
            )
        if (
            self.previous_floor_sequence == 0
            and self.previous_floor_root != "0" * 64
        ):
            raise ValueError(
                "genesis previous floor must use genesis root"
            )
        for name in (
            "completed_at",
            "issued_at",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) < 0.0
            ):
                raise ValueError(
                    f"{name} must be finite and non-negative"
                )
            object.__setattr__(
                self,
                name,
                float(value),
            )
        if self.issued_at < self.completed_at:
            raise ValueError(
                "proof may not be issued before workflow completion"
            )

    @property
    def destructive_action_authorized(self) -> bool:
        return False

    @property
    def authority(self) -> str:
        return "post-operation-compaction-evidence"

    @property
    def binding_dict(self) -> dict[str, object]:
        return {
            "workflow_id": self.workflow_id,
            "workflow_digest": self.workflow_digest,
            "chain_id": self.chain_id,
            "operator_id": self.operator_id,
            "reservation_id": self.reservation_id,
            "reservation_digest": self.reservation_digest,
            "reservation_generation": self.reservation_generation,
            "certificate_id": self.certificate_id,
            "certificate_digest": self.certificate_digest,
            "authorization_id": self.authorization_id,
            "authorization_digest": self.authorization_digest,
            "archive_id": self.archive_id,
            "archive_manifest_digest": self.archive_manifest_digest,
            "pruning_operation_id": self.pruning_operation_id,
            "pruning_manifest_digest": self.pruning_manifest_digest,
            "floor_id": self.floor_id,
            "floor_digest": self.floor_digest,
            "current_sequence": self.current_sequence,
            "current_root": self.current_root,
            "cutoff_sequence": self.cutoff_sequence,
            "cutoff_root": self.cutoff_root,
            "previous_floor_sequence": self.previous_floor_sequence,
            "previous_floor_root": self.previous_floor_root,
            "delete_count": self.delete_count,
            "deleted_items": self.deleted_items,
            "fencing_token": self.fencing_token,
            "archive_verification_digest": (
                self.archive_verification_digest
            ),
            "completed_at": self.completed_at,
        }

    @property
    def binding_digest(self) -> str:
        raw = json.dumps(
            self.binding_dict,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(include_digest=False),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data = {
            "schema_version": self.schema_version,
            "proof_id": self.proof_id,
            **self.binding_dict,
            "binding_digest": self.binding_digest,
            "issued_at": self.issued_at,
            "destructive_action_authorized": False,
            "authority": self.authority,
        }
        if include_digest:
            data["digest"] = self.digest
        return data

    @classmethod
    def derive_id(
        cls,
        *,
        workflow_id: str,
        workflow_digest: str,
        reservation_id: str,
        certificate_id: str,
        authorization_id: str,
        pruning_operation_id: str,
        floor_id: str,
    ) -> str:
        payload = {
            "workflow_id": workflow_id,
            "workflow_digest": workflow_digest,
            "reservation_id": reservation_id,
            "certificate_id": certificate_id,
            "authorization_id": authorization_id,
            "pruning_operation_id": pruning_operation_id,
            "floor_id": floor_id,
            "authority": "post-operation-compaction-evidence",
        }
        raw = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class SignedDurableCompactionProof:
    proof: DurableCompactionProof
    signature: SignedArtifact

    def __post_init__(self) -> None:
        if not isinstance(
            self.proof,
            DurableCompactionProof,
        ):
            raise TypeError(
                "proof must be DurableCompactionProof"
            )
        if not isinstance(
            self.signature,
            SignedArtifact,
        ):
            raise TypeError(
                "signature must be SignedArtifact"
            )

    @property
    def proof_id(self) -> str:
        return self.proof.proof_id

    @property
    def destructive_action_authorized(self) -> bool:
        return False

    def to_dict(self) -> dict[str, object]:
        return {
            "proof": self.proof.to_dict(),
            "signature": self.signature.to_dict(),
            "destructive_action_authorized": False,
        }


@dataclass(frozen=True)
class DurableCompactionProofVerification:
    valid: bool
    proof_id: str
    chain_id: str
    workflow_id: str
    component_signatures_valid: bool
    workflow_complete: bool
    pruning_complete: bool
    archive_valid: bool
    floor_binding_valid: bool
    reservation_binding_valid: bool
    authority_binding_valid: bool
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.valid, bool):
            raise ValueError("valid must be bool")
        object.__setattr__(
            self,
            "proof_id",
            _digest("proof_id", self.proof_id),
        )
        object.__setattr__(
            self,
            "workflow_id",
            _digest("workflow_id", self.workflow_id),
        )
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        for name in (
            "component_signatures_valid",
            "workflow_complete",
            "pruning_complete",
            "archive_valid",
            "floor_binding_valid",
            "reservation_binding_valid",
            "authority_binding_valid",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be bool")
        object.__setattr__(
            self,
            "reasons",
            tuple(self.reasons),
        )

    @property
    def destructive_action_authorized(self) -> bool:
        return False

    def to_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "proof_id": self.proof_id,
            "chain_id": self.chain_id,
            "workflow_id": self.workflow_id,
            "component_signatures_valid": (
                self.component_signatures_valid
            ),
            "workflow_complete": self.workflow_complete,
            "pruning_complete": self.pruning_complete,
            "archive_valid": self.archive_valid,
            "floor_binding_valid": self.floor_binding_valid,
            "reservation_binding_valid": (
                self.reservation_binding_valid
            ),
            "authority_binding_valid": (
                self.authority_binding_valid
            ),
            "reasons": list(self.reasons),
            "destructive_action_authorized": False,
        }


class DurableCompactionProofError(RuntimeError):
    pass


class DurableCompactionProofBuilder:
    """Build and verify non-authorizing post-compaction audit proofs."""

    def __init__(
        self,
        proof_signer: ArtifactSigner,
        *,
        certificate_signer: ArtifactSigner | None = None,
        authorization_signer: ArtifactSigner | None = None,
        reservation_signer: ArtifactSigner | None = None,
        archive_signer: ArtifactSigner | None = None,
        floor_signer: ArtifactSigner | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(
            proof_signer,
            ArtifactSigner,
        ):
            raise TypeError(
                "proof_signer must be ArtifactSigner"
            )
        for name, signer in (
            ("certificate_signer", certificate_signer),
            ("authorization_signer", authorization_signer),
            ("reservation_signer", reservation_signer),
            ("archive_signer", archive_signer),
            ("floor_signer", floor_signer),
        ):
            if signer is not None and not isinstance(
                signer,
                ArtifactSigner,
            ):
                raise TypeError(
                    f"{name} must be ArtifactSigner or None"
                )
        if not callable(clock):
            raise TypeError("clock must be callable")
        self.proof_signer = proof_signer
        self.certificate_signer = certificate_signer
        self.authorization_signer = authorization_signer
        self.reservation_signer = reservation_signer
        self.archive_signer = archive_signer
        self.floor_signer = floor_signer
        self._clock = clock

    @staticmethod
    def _archive_verification_digest(
        verification: DurableArchiveVerification,
    ) -> str:
        raw = json.dumps(
            verification.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _component_signature(
        signer: ArtifactSigner | None,
        signature: SignedArtifact,
        *,
        label: str,
        expected_type: str,
        expected_digest: str,
        reasons: list[str],
    ) -> bool:
        if signer is None:
            reasons.append(
                f"{label} signature signer unavailable"
            )
            return False
        try:
            signer.verify(signature)
        except ArtifactSignatureError:
            reasons.append(
                f"{label} signature verification failed"
            )
            return False
        if signature.artifact_type != expected_type:
            reasons.append(
                f"{label} signature artifact type mismatch"
            )
            return False
        if signature.artifact_digest != expected_digest:
            reasons.append(
                f"{label} signature artifact digest mismatch"
            )
            return False
        return True

    @staticmethod
    def _compare(
        reasons: list[str],
        label: str,
        *values,
    ) -> bool:
        if not values:
            return True
        first = values[0]
        if all(value == first for value in values[1:]):
            return True
        reasons.append(
            f"{label} binding mismatch"
        )
        return False

    def inspect(
        self,
        item: SignedDurableCompactionProof,
        *,
        workflow: DurableCompactionWorkflow,
        reservation: SignedDurableCompactionReservation,
        certificate: SignedDurableCompactionCertificate,
        authorization: SignedDurablePruningAuthorization,
        archive: SignedDurableArchiveManifest,
        archive_verification: DurableArchiveVerification,
        pruning: DurablePruningResult,
    ) -> DurableCompactionProofVerification:
        if not isinstance(
            item,
            SignedDurableCompactionProof,
        ):
            raise TypeError(
                "item must be SignedDurableCompactionProof"
            )
        reasons: list[str] = []

        try:
            self.proof_signer.verify(
                item.signature
            )
            proof_signature_valid = (
                item.signature.artifact_type
                == "shell-ai-durable-compaction-proof"
                and item.signature.artifact_digest
                == item.proof.digest
            )
            if not proof_signature_valid:
                reasons.append(
                    "proof signature artifact binding mismatch"
                )
        except ArtifactSignatureError:
            proof_signature_valid = False
            reasons.append(
                "proof signature verification failed"
            )

        component_signature_results = (
            self._component_signature(
                self.reservation_signer,
                reservation.signature,
                label="reservation",
                expected_type="durable-compaction-reservation",
                expected_digest=reservation.reservation.digest,
                reasons=reasons,
            ),
            self._component_signature(
                self.certificate_signer,
                certificate.signature,
                label="certificate",
                expected_type="durable-compaction-readiness",
                expected_digest=certificate.certificate.digest,
                reasons=reasons,
            ),
            self._component_signature(
                self.authorization_signer,
                authorization.signature,
                label="authorization",
                expected_type="durable-pruning-authorization",
                expected_digest=authorization.authorization.digest,
                reasons=reasons,
            ),
            self._component_signature(
                self.archive_signer,
                archive.signature,
                label="archive",
                expected_type="durable-archive-manifest",
                expected_digest=archive.manifest.digest,
                reasons=reasons,
            ),
            self._component_signature(
                self.floor_signer,
                pruning.floor.signature,
                label="hot floor",
                expected_type="durable-hot-floor",
                expected_digest=pruning.floor.floor.digest,
                reasons=reasons,
            ),
        )
        component_signatures_valid = all(
            component_signature_results
        )

        proof = item.proof
        reservation_value = reservation.reservation
        certificate_value = certificate.certificate
        authorization_value = authorization.authorization
        archive_value = archive.manifest
        operation = pruning.operation
        manifest = pruning.manifest
        floor = pruning.floor.floor

        workflow_complete = workflow.complete
        if not workflow_complete:
            reasons.append(
                "workflow is not complete"
            )
        pruning_complete = pruning.ok
        if not pruning_complete:
            reasons.append(
                "pruning result is not complete and live-verified"
            )
        archive_valid = archive_verification.valid
        if not archive_valid:
            reasons.append(
                "archive verification is not valid"
            )

        chain_binding = self._compare(
            reasons,
            "chain_id",
            proof.chain_id,
            workflow.chain_id,
            reservation_value.chain_id,
            certificate_value.chain_id,
            authorization_value.chain_id,
            archive_value.chain_id,
            archive_verification.chain_id,
            operation.chain_id,
            manifest.chain_id,
            floor.chain_id,
        )
        workflow_binding = self._compare(
            reasons,
            "workflow",
            proof.workflow_id,
            workflow.workflow_id,
        ) and self._compare(
            reasons,
            "workflow digest",
            proof.workflow_digest,
            workflow.digest,
        )
        reservation_binding_valid = (
            self._compare(
                reasons,
                "reservation",
                proof.reservation_id,
                reservation_value.reservation_id,
            )
            and self._compare(
                reasons,
                "reservation digest",
                proof.reservation_digest,
                reservation_value.digest,
            )
            and self._compare(
                reasons,
                "reservation generation",
                proof.reservation_generation,
                reservation_value.generation,
            )
            and self._compare(
                reasons,
                "reservation operator",
                proof.operator_id,
                workflow.operator_id,
                reservation_value.operator_id,
            )
        )
        certificate_binding = (
            self._compare(
                reasons,
                "certificate id",
                proof.certificate_id,
                workflow.certificate_id,
                certificate_value.certificate_id,
                authorization_value.certificate_id,
                floor.compaction_certificate_id,
            )
            and self._compare(
                reasons,
                "certificate digest",
                proof.certificate_digest,
                workflow.certificate_digest,
                certificate_value.digest,
                authorization_value.certificate_digest,
            )
        )
        authorization_binding = (
            self._compare(
                reasons,
                "authorization id",
                proof.authorization_id,
                workflow.authorization_id,
                authorization_value.authorization_id,
                operation.authorization_id,
                manifest.authorization_id,
                floor.pruning_authorization_id,
            )
            and self._compare(
                reasons,
                "authorization digest",
                proof.authorization_digest,
                workflow.authorization_digest,
                authorization_value.digest,
            )
        )
        archive_binding = (
            self._compare(
                reasons,
                "archive id",
                proof.archive_id,
                workflow.archive_id,
                certificate_value.archive_id,
                authorization_value.archive_id,
                archive_value.archive_id,
                archive_verification.archive_id,
                manifest.archive_id,
                floor.archive_id,
            )
            and self._compare(
                reasons,
                "archive manifest digest",
                proof.archive_manifest_digest,
                workflow.archive_manifest_digest,
                certificate_value.archive_manifest_digest,
                authorization_value.archive_manifest_digest,
                archive_value.digest,
                manifest.archive_manifest_digest,
                floor.archive_manifest_digest,
            )
            and self._compare(
                reasons,
                "archive checkpoint sequence",
                proof.cutoff_sequence,
                archive_value.checkpoint_sequence,
                archive_verification.checkpoint_sequence,
            )
            and self._compare(
                reasons,
                "archive checkpoint root",
                proof.cutoff_root,
                archive_value.checkpoint_root,
                archive_verification.checkpoint_root,
            )
        )
        operation_binding = (
            self._compare(
                reasons,
                "pruning operation id",
                proof.pruning_operation_id,
                workflow.pruning_operation_id,
                operation.operation_id,
                manifest.operation_id,
                floor.operation_id,
            )
            and self._compare(
                reasons,
                "pruning manifest digest",
                proof.pruning_manifest_digest,
                workflow.pruning_manifest_digest,
                operation.manifest_digest,
                manifest.digest,
            )
        )
        head_binding = (
            self._compare(
                reasons,
                "current sequence",
                proof.current_sequence,
                workflow.current_sequence,
                certificate_value.current_sequence,
                authorization_value.current_sequence,
                manifest.current_sequence,
            )
            and self._compare(
                reasons,
                "current root",
                proof.current_root,
                workflow.current_root,
                certificate_value.current_root,
                authorization_value.current_root,
                manifest.current_root,
            )
        )
        floor_binding_valid = (
            self._compare(
                reasons,
                "cutoff sequence",
                proof.cutoff_sequence,
                workflow.cutoff_sequence,
                certificate_value.cutoff_sequence,
                authorization_value.cutoff_sequence,
                manifest.cutoff_sequence,
                floor.sequence,
            )
            and self._compare(
                reasons,
                "cutoff root",
                proof.cutoff_root,
                workflow.cutoff_root,
                certificate_value.cutoff_root,
                authorization_value.cutoff_root,
                manifest.cutoff_root,
                floor.root_hash,
            )
            and self._compare(
                reasons,
                "previous floor sequence",
                proof.previous_floor_sequence,
                workflow.previous_floor_sequence,
                authorization_value.previous_floor_sequence,
                manifest.previous_floor_sequence,
                floor.previous_sequence,
            )
            and self._compare(
                reasons,
                "previous floor root",
                proof.previous_floor_root,
                workflow.previous_floor_root,
                authorization_value.previous_floor_root,
                manifest.previous_floor_root,
                floor.previous_root_hash,
            )
            and self._compare(
                reasons,
                "floor id",
                proof.floor_id,
                workflow.floor_id,
                operation.floor_id,
                floor.floor_id,
            )
            and self._compare(
                reasons,
                "floor digest",
                proof.floor_digest,
                floor.digest,
            )
            and self._compare(
                reasons,
                "fencing token",
                proof.fencing_token,
                operation.fencing_token,
                floor.fencing_token,
            )
        )
        deletion_binding = (
            self._compare(
                reasons,
                "delete count",
                proof.delete_count,
                workflow.delete_count,
                authorization_value.delete_count,
                manifest.delete_count,
            )
            and self._compare(
                reasons,
                "deleted items",
                proof.deleted_items,
                workflow.deleted_items,
                operation.deleted_items,
                manifest.delete_count,
            )
        )

        archive_verification_digest = (
            self._archive_verification_digest(
                archive_verification
            )
        )
        archive_verification_binding = self._compare(
            reasons,
            "archive verification digest",
            proof.archive_verification_digest,
            archive_verification_digest,
        )

        authority_binding_valid = all(
            (
                chain_binding,
                workflow_binding,
                certificate_binding,
                authorization_binding,
                archive_binding,
                operation_binding,
                head_binding,
                deletion_binding,
                archive_verification_binding,
            )
        )

        expected_id = DurableCompactionProof.derive_id(
            workflow_id=proof.workflow_id,
            workflow_digest=proof.workflow_digest,
            reservation_id=proof.reservation_id,
            certificate_id=proof.certificate_id,
            authorization_id=proof.authorization_id,
            pruning_operation_id=proof.pruning_operation_id,
            floor_id=proof.floor_id,
        )
        if expected_id != proof.proof_id:
            reasons.append(
                "proof_id does not match bound component identities"
            )
            authority_binding_valid = False

        valid = all(
            (
                proof_signature_valid,
                component_signatures_valid,
                workflow_complete,
                pruning_complete,
                archive_valid,
                floor_binding_valid,
                reservation_binding_valid,
                authority_binding_valid,
            )
        ) and not reasons

        return DurableCompactionProofVerification(
            valid,
            proof.proof_id,
            proof.chain_id,
            proof.workflow_id,
            component_signatures_valid,
            workflow_complete,
            pruning_complete,
            archive_valid,
            floor_binding_valid,
            reservation_binding_valid,
            authority_binding_valid,
            tuple(reasons),
        )

    def build(
        self,
        *,
        workflow: DurableCompactionWorkflow,
        reservation: SignedDurableCompactionReservation,
        certificate: SignedDurableCompactionCertificate,
        authorization: SignedDurablePruningAuthorization,
        archive: SignedDurableArchiveManifest,
        archive_verification: DurableArchiveVerification,
        pruning: DurablePruningResult,
    ) -> SignedDurableCompactionProof:
        completed_at = workflow.updated_at
        issued_at = float(self._clock())
        if not math.isfinite(issued_at) or issued_at < 0.0:
            raise ValueError(
                "proof clock must return finite non-negative time"
            )

        proof_id = DurableCompactionProof.derive_id(
            workflow_id=workflow.workflow_id,
            workflow_digest=workflow.digest,
            reservation_id=reservation.reservation.reservation_id,
            certificate_id=certificate.certificate.certificate_id,
            authorization_id=authorization.authorization.authorization_id,
            pruning_operation_id=pruning.operation.operation_id,
            floor_id=pruning.floor.floor.floor_id,
        )
        proof = DurableCompactionProof(
            1,
            proof_id,
            workflow.workflow_id,
            workflow.digest,
            workflow.chain_id,
            workflow.operator_id,
            reservation.reservation.reservation_id,
            reservation.reservation.digest,
            reservation.reservation.generation,
            certificate.certificate.certificate_id,
            certificate.certificate.digest,
            authorization.authorization.authorization_id,
            authorization.authorization.digest,
            archive.manifest.archive_id,
            archive.manifest.digest,
            pruning.operation.operation_id,
            pruning.manifest.digest,
            pruning.floor.floor.floor_id,
            pruning.floor.floor.digest,
            workflow.current_sequence,
            workflow.current_root,
            workflow.cutoff_sequence,
            workflow.cutoff_root,
            workflow.previous_floor_sequence,
            workflow.previous_floor_root,
            workflow.delete_count,
            workflow.deleted_items,
            pruning.floor.floor.fencing_token,
            self._archive_verification_digest(
                archive_verification
            ),
            completed_at,
            issued_at,
        )
        signed = SignedDurableCompactionProof(
            proof,
            self.proof_signer.sign(
                "shell-ai-durable-compaction-proof",
                proof.digest,
                metadata={
                    "proof_id": proof.proof_id,
                    "chain_id": proof.chain_id,
                    "workflow_id": proof.workflow_id,
                    "authority": proof.authority,
                },
            ),
        )
        verification = self.inspect(
            signed,
            workflow=workflow,
            reservation=reservation,
            certificate=certificate,
            authorization=authorization,
            archive=archive,
            archive_verification=archive_verification,
            pruning=pruning,
        )
        if not verification.valid:
            detail = (
                verification.reasons[0]
                if verification.reasons
                else "compaction proof validation failed"
            )
            raise DurableCompactionProofError(
                detail
            )
        return signed

    def require(
        self,
        item: SignedDurableCompactionProof,
        *,
        workflow: DurableCompactionWorkflow,
        reservation: SignedDurableCompactionReservation,
        certificate: SignedDurableCompactionCertificate,
        authorization: SignedDurablePruningAuthorization,
        archive: SignedDurableArchiveManifest,
        archive_verification: DurableArchiveVerification,
        pruning: DurablePruningResult,
    ) -> DurableCompactionProofVerification:
        verification = self.inspect(
            item,
            workflow=workflow,
            reservation=reservation,
            certificate=certificate,
            authorization=authorization,
            archive=archive,
            archive_verification=archive_verification,
            pruning=pruning,
        )
        if not verification.valid:
            detail = (
                verification.reasons[0]
                if verification.reasons
                else "compaction proof is invalid"
            )
            raise DurableCompactionProofError(
                detail
            )
        return verification
