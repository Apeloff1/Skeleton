"""Signed completion artifacts for cross-chain durable evidence epochs.

A completed compaction group proves that several evidence chains crossed their
hot-floor boundaries under a coordinated saga.  This module turns that runtime
state into one immutable, signed, restart-verifiable artifact.

The epoch artifact does not create pruning authority.  It is post-commit
evidence binding:

* the persisted completed group and its digest;
* every member workflow and stable authority binding;
* the archive and archive manifest used to justify deletion;
* readiness certificate and destructive pruning authorization identities;
* immutable pruning operation/manifest;
* signed historical hot-floor record and fencing token;
* the live chain head observed for the completed workflow.

Old epoch artifacts remain historically verifiable after later appends or
later compactions.  A CAS latest-head per logical epoch id prevents publication
rollback when several completed groups reuse the same epoch namespace.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
from typing import Mapping, Sequence

from skeleton.shells.ai.distributed_state import DistributedStateConflict
from skeleton.shells.ai.durable_compaction_group import (
    DurableCompactionGroupCoordinator,
    DurableCompactionGroupPhase,
    DurableCompactionGroupRequest,
)
from skeleton.shells.ai.durable_compaction_operator import (
    DurableCompactionWorkflowPhase,
)
from skeleton.shells.ai.durable_pruning import DurablePruningPhase
from skeleton.shells.ai.signed_artifact import (
    ArtifactSignatureError,
    ArtifactSigner,
    SignedArtifact,
)
from skeleton.shells.ai.store_protocol import VersionedStateBackend


def _digest(
    name: str,
    value: str,
    *,
    optional: bool = False,
) -> str:
    if optional and not value:
        return ""
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{name} must be 64-character digest")
    return value.lower()


def _identity(
    name: str,
    value: str,
    *,
    maximum: int,
) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
    ):
        raise ValueError(f"invalid {name}")
    return value


@dataclass(frozen=True)
class DurableEvidenceEpochMember:
    chain_id: str
    workflow_id: str
    workflow_digest: str
    workflow_binding_digest: str
    retention_plan_digest: str
    current_sequence: int
    current_root: str
    cutoff_sequence: int
    cutoff_root: str
    archive_id: str
    archive_manifest_digest: str
    certificate_id: str
    certificate_digest: str
    authorization_id: str
    authorization_digest: str
    pruning_operation_id: str
    pruning_manifest_digest: str
    floor_id: str
    floor_digest: str
    floor_fencing_token: int
    deleted_items: int
    delete_count: int

    def __post_init__(self) -> None:
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        _identity(
            "archive_id",
            self.archive_id,
            maximum=256,
        )
        for name in (
            "workflow_id",
            "workflow_digest",
            "workflow_binding_digest",
            "retention_plan_digest",
            "current_root",
            "cutoff_root",
            "archive_manifest_digest",
            "certificate_id",
            "certificate_digest",
            "authorization_id",
            "authorization_digest",
            "pruning_operation_id",
            "pruning_manifest_digest",
            "floor_id",
            "floor_digest",
        ):
            object.__setattr__(
                self,
                name,
                _digest(name, getattr(self, name)),
            )
        for name in (
            "current_sequence",
            "cutoff_sequence",
            "floor_fencing_token",
            "deleted_items",
            "delete_count",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ValueError(
                    f"{name} must be non-negative integer"
                )
        if self.current_sequence <= 0:
            raise ValueError(
                "epoch member current_sequence must be positive"
            )
        if (
            self.cutoff_sequence <= 0
            or self.cutoff_sequence
            > self.current_sequence
        ):
            raise ValueError(
                "epoch member cutoff_sequence outside current range"
            )
        if self.floor_fencing_token <= 0:
            raise ValueError(
                "epoch member floor fencing token must be positive"
            )
        if (
            self.delete_count <= 0
            or self.deleted_items
            != self.delete_count
        ):
            raise ValueError(
                "epoch member must bind completed non-empty deletion interval"
            )

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
        data: dict[str, object] = {
            "chain_id": self.chain_id,
            "workflow_id": self.workflow_id,
            "workflow_digest": self.workflow_digest,
            "workflow_binding_digest": self.workflow_binding_digest,
            "retention_plan_digest": self.retention_plan_digest,
            "current_sequence": self.current_sequence,
            "current_root": self.current_root,
            "cutoff_sequence": self.cutoff_sequence,
            "cutoff_root": self.cutoff_root,
            "archive_id": self.archive_id,
            "archive_manifest_digest": self.archive_manifest_digest,
            "certificate_id": self.certificate_id,
            "certificate_digest": self.certificate_digest,
            "authorization_id": self.authorization_id,
            "authorization_digest": self.authorization_digest,
            "pruning_operation_id": self.pruning_operation_id,
            "pruning_manifest_digest": self.pruning_manifest_digest,
            "floor_id": self.floor_id,
            "floor_digest": self.floor_digest,
            "floor_fencing_token": self.floor_fencing_token,
            "deleted_items": self.deleted_items,
            "delete_count": self.delete_count,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class DurableEvidenceEpoch:
    schema_version: int
    record_id: str
    epoch_id: str
    group_id: str
    group_digest: str
    group_binding_digest: str
    operator_id: str
    completed_at: float
    members: tuple[DurableEvidenceEpochMember, ...]

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(
                "unsupported durable evidence epoch schema"
            )
        object.__setattr__(
            self,
            "record_id",
            _digest("record_id", self.record_id),
        )
        object.__setattr__(
            self,
            "group_id",
            _digest("group_id", self.group_id),
        )
        object.__setattr__(
            self,
            "group_digest",
            _digest("group_digest", self.group_digest),
        )
        object.__setattr__(
            self,
            "group_binding_digest",
            _digest(
                "group_binding_digest",
                self.group_binding_digest,
            ),
        )
        _identity(
            "epoch_id",
            self.epoch_id,
            maximum=256,
        )
        _identity(
            "operator_id",
            self.operator_id,
            maximum=256,
        )
        if (
            isinstance(self.completed_at, bool)
            or not isinstance(self.completed_at, (int, float))
            or not math.isfinite(float(self.completed_at))
            or float(self.completed_at) < 0.0
        ):
            raise ValueError(
                "completed_at must be finite and non-negative"
            )
        object.__setattr__(
            self,
            "completed_at",
            float(self.completed_at),
        )
        members = tuple(self.members)
        if len(members) < 2:
            raise ValueError(
                "evidence epoch requires at least two member chains"
            )
        chain_ids = tuple(
            item.chain_id
            for item in members
        )
        if (
            chain_ids
            != tuple(sorted(chain_ids))
            or len(chain_ids)
            != len(set(chain_ids))
        ):
            raise ValueError(
                "evidence epoch members must be uniquely sorted by chain_id"
            )
        object.__setattr__(
            self,
            "members",
            members,
        )
        expected = self.derive_record_id(
            epoch_id=self.epoch_id,
            group_id=self.group_id,
            group_digest=self.group_digest,
            group_binding_digest=self.group_binding_digest,
            operator_id=self.operator_id,
            completed_at=self.completed_at,
            members=members,
        )
        if expected != self.record_id:
            raise ValueError(
                "evidence epoch record_id does not match content"
            )

    @staticmethod
    def derive_record_id(
        *,
        epoch_id: str,
        group_id: str,
        group_digest: str,
        group_binding_digest: str,
        operator_id: str,
        completed_at: float,
        members: Sequence[
            DurableEvidenceEpochMember
        ],
    ) -> str:
        raw = json.dumps(
            {
                "epoch_id": epoch_id,
                "group_id": group_id,
                "group_digest": group_digest,
                "group_binding_digest": group_binding_digest,
                "operator_id": operator_id,
                "completed_at": float(completed_at),
                "members": [
                    member.digest
                    for member in members
                ],
                "authority": (
                    "durable-evidence-epoch-completion"
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.unsigned_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def unsigned_dict(
        self,
    ) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "record_id": self.record_id,
            "epoch_id": self.epoch_id,
            "group_id": self.group_id,
            "group_digest": self.group_digest,
            "group_binding_digest": self.group_binding_digest,
            "operator_id": self.operator_id,
            "completed_at": self.completed_at,
            "members": [
                member.to_dict()
                for member in self.members
            ],
        }

    def to_dict(self) -> dict[str, object]:
        return {
            **self.unsigned_dict(),
            "digest": self.digest,
            "destructive_action_authorized": False,
        }


@dataclass(frozen=True)
class SignedDurableEvidenceEpoch:
    epoch: DurableEvidenceEpoch
    signature: SignedArtifact

    def __post_init__(self) -> None:
        if not isinstance(
            self.epoch,
            DurableEvidenceEpoch,
        ):
            raise TypeError(
                "epoch must be DurableEvidenceEpoch"
            )
        if not isinstance(
            self.signature,
            SignedArtifact,
        ):
            raise TypeError(
                "signature must be SignedArtifact"
            )

    @property
    def record_id(self) -> str:
        return self.epoch.record_id

    @property
    def epoch_id(self) -> str:
        return self.epoch.epoch_id

    @property
    def destructive_action_authorized(self) -> bool:
        return False

    def to_dict(self) -> dict[str, object]:
        return {
            "epoch": self.epoch.to_dict(),
            "signature": self.signature.to_dict(),
            "destructive_action_authorized": False,
        }


@dataclass(frozen=True)
class DurableEvidenceEpochHead:
    epoch_id: str
    record_id: str
    generation: int
    completed_at: float

    def __post_init__(self) -> None:
        _identity(
            "epoch_id",
            self.epoch_id,
            maximum=256,
        )
        object.__setattr__(
            self,
            "record_id",
            _digest("record_id", self.record_id),
        )
        if (
            isinstance(self.generation, bool)
            or not isinstance(self.generation, int)
            or self.generation <= 0
        ):
            raise ValueError(
                "epoch head generation must be positive"
            )
        if (
            isinstance(self.completed_at, bool)
            or not isinstance(self.completed_at, (int, float))
            or not math.isfinite(float(self.completed_at))
            or float(self.completed_at) < 0.0
        ):
            raise ValueError(
                "epoch head completed_at must be non-negative"
            )
        object.__setattr__(
            self,
            "completed_at",
            float(self.completed_at),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "epoch_id": self.epoch_id,
            "record_id": self.record_id,
            "generation": self.generation,
            "completed_at": self.completed_at,
        }


class DurableEvidenceEpochMemberState(str, Enum):
    VALID = "valid"
    STALE_CURRENT_FLOOR = "stale_current_floor"
    INVALID = "invalid"


@dataclass(frozen=True)
class DurableEvidenceEpochMemberVerification:
    chain_id: str
    state: DurableEvidenceEpochMemberState
    workflow_valid: bool
    archive_valid: bool
    certificate_valid: bool
    authorization_valid: bool
    pruning_valid: bool
    floor_valid: bool
    live_head_valid: bool
    current_floor_exact: bool
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        object.__setattr__(
            self,
            "state",
            DurableEvidenceEpochMemberState(
                self.state
            ),
        )
        for name in (
            "workflow_valid",
            "archive_valid",
            "certificate_valid",
            "authorization_valid",
            "pruning_valid",
            "floor_valid",
            "live_head_valid",
            "current_floor_exact",
        ):
            if not isinstance(
                getattr(self, name),
                bool,
            ):
                raise ValueError(
                    f"{name} must be bool"
                )
        object.__setattr__(
            self,
            "reasons",
            tuple(self.reasons),
        )

    @property
    def historically_valid(self) -> bool:
        return (
            self.workflow_valid
            and self.archive_valid
            and self.certificate_valid
            and self.authorization_valid
            and self.pruning_valid
            and self.floor_valid
            and self.live_head_valid
            and not self.reasons
        )

    @property
    def current(self) -> bool:
        return (
            self.historically_valid
            and self.current_floor_exact
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "chain_id": self.chain_id,
            "state": self.state.value,
            "historically_valid": self.historically_valid,
            "current": self.current,
            "workflow_valid": self.workflow_valid,
            "archive_valid": self.archive_valid,
            "certificate_valid": self.certificate_valid,
            "authorization_valid": self.authorization_valid,
            "pruning_valid": self.pruning_valid,
            "floor_valid": self.floor_valid,
            "live_head_valid": self.live_head_valid,
            "current_floor_exact": self.current_floor_exact,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class DurableEvidenceEpochVerification:
    item: SignedDurableEvidenceEpoch
    signature_valid: bool
    group_valid: bool
    latest_for_epoch: bool
    members: tuple[
        DurableEvidenceEpochMemberVerification,
        ...,
    ]
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(
            self.item,
            SignedDurableEvidenceEpoch,
        ):
            raise TypeError(
                "item must be SignedDurableEvidenceEpoch"
            )
        if not isinstance(
            self.signature_valid,
            bool,
        ):
            raise ValueError(
                "signature_valid must be bool"
            )
        if not isinstance(
            self.group_valid,
            bool,
        ):
            raise ValueError(
                "group_valid must be bool"
            )
        if not isinstance(
            self.latest_for_epoch,
            bool,
        ):
            raise ValueError(
                "latest_for_epoch must be bool"
            )
        object.__setattr__(
            self,
            "members",
            tuple(self.members),
        )
        object.__setattr__(
            self,
            "reasons",
            tuple(self.reasons),
        )

    @property
    def historically_valid(self) -> bool:
        return (
            self.signature_valid
            and self.group_valid
            and all(
                member.historically_valid
                for member in self.members
            )
            and not self.reasons
        )

    @property
    def current(self) -> bool:
        return (
            self.historically_valid
            and self.latest_for_epoch
            and all(
                member.current
                for member in self.members
            )
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "historically_valid": self.historically_valid,
            "current": self.current,
            "signature_valid": self.signature_valid,
            "group_valid": self.group_valid,
            "latest_for_epoch": self.latest_for_epoch,
            "item": self.item.to_dict(),
            "members": [
                member.to_dict()
                for member in self.members
            ],
            "reasons": list(self.reasons),
        }


class DurableEvidenceEpochError(RuntimeError):
    pass


class DurableEvidenceEpochConflict(
    DurableEvidenceEpochError
):
    pass


class DurableEvidenceEpochStore:
    """Publish and verify immutable cross-chain evidence epoch completions."""

    def __init__(
        self,
        backend: VersionedStateBackend,
        signer: ArtifactSigner,
        coordinator: DurableCompactionGroupCoordinator,
        *,
        namespace: str = (
            "shell-ai-durable-evidence-epochs"
        ),
        max_cas_retries: int = 32,
    ) -> None:
        if not isinstance(
            backend,
            VersionedStateBackend,
        ):
            raise TypeError(
                "backend must satisfy VersionedStateBackend"
            )
        if not isinstance(
            signer,
            ArtifactSigner,
        ):
            raise TypeError(
                "signer must be ArtifactSigner"
            )
        if not isinstance(
            coordinator,
            DurableCompactionGroupCoordinator,
        ):
            raise TypeError(
                "coordinator must be DurableCompactionGroupCoordinator"
            )
        if (
            not namespace
            or len(namespace) > 128
        ):
            raise ValueError(
                "invalid evidence epoch namespace"
            )
        if (
            isinstance(max_cas_retries, bool)
            or not isinstance(max_cas_retries, int)
            or not 1 <= max_cas_retries <= 128
        ):
            raise ValueError(
                "max_cas_retries outside supported range"
            )
        self.backend = backend
        self.signer = signer
        self.coordinator = coordinator
        self.namespace = namespace
        self.max_cas_retries = max_cas_retries

    @staticmethod
    def _record_key(
        record_id: str,
    ) -> str:
        return (
            "epoch:"
            + _digest("record_id", record_id)
        )

    @staticmethod
    def _epoch_hash(
        epoch_id: str,
    ) -> str:
        _identity(
            "epoch_id",
            epoch_id,
            maximum=256,
        )
        return hashlib.sha256(
            epoch_id.encode()
        ).hexdigest()

    @classmethod
    def _head_key(
        cls,
        epoch_id: str,
    ) -> str:
        return (
            "head:"
            + cls._epoch_hash(epoch_id)
        )

    @staticmethod
    def _request_map(
        requests: Sequence[
            DurableCompactionGroupRequest
        ],
    ) -> dict[
        str,
        DurableCompactionGroupRequest,
    ]:
        result = {}
        for request in requests:
            if not isinstance(
                request,
                DurableCompactionGroupRequest,
            ):
                raise TypeError(
                    "requests must contain DurableCompactionGroupRequest"
                )
            if request.chain_id in result:
                raise ValueError(
                    "duplicate chain_id in epoch requests"
                )
            result[request.chain_id] = request
        return result

    def _verify_signature(
        self,
        item: SignedDurableEvidenceEpoch,
    ) -> None:
        signature = item.signature
        epoch = item.epoch
        if (
            signature.artifact_type
            != "durable-evidence-epoch"
        ):
            raise DurableEvidenceEpochError(
                "evidence epoch artifact type mismatch"
            )
        if (
            signature.artifact_digest
            != epoch.digest
        ):
            raise DurableEvidenceEpochError(
                "evidence epoch signature digest mismatch"
            )
        expected_metadata = {
            "authority": (
                "durable-evidence-epoch-completion"
            ),
            "record_id": epoch.record_id,
            "epoch_id": epoch.epoch_id,
            "group_id": epoch.group_id,
        }
        if (
            dict(signature.metadata)
            != expected_metadata
        ):
            raise DurableEvidenceEpochError(
                "evidence epoch signature metadata mismatch"
            )
        try:
            self.signer.verify(
                signature
            )
        except ArtifactSignatureError as exc:
            raise DurableEvidenceEpochError(
                "evidence epoch signature verification failed"
            ) from exc

    def _sign(
        self,
        epoch: DurableEvidenceEpoch,
    ) -> SignedDurableEvidenceEpoch:
        return SignedDurableEvidenceEpoch(
            epoch,
            self.signer.sign(
                "durable-evidence-epoch",
                epoch.digest,
                metadata={
                    "authority": (
                        "durable-evidence-epoch-completion"
                    ),
                    "record_id": epoch.record_id,
                    "epoch_id": epoch.epoch_id,
                    "group_id": epoch.group_id,
                },
            ),
        )

    def get(
        self,
        record_id: str,
    ) -> SignedDurableEvidenceEpoch | None:
        record = self.backend.get(
            self.namespace,
            self._record_key(
                record_id
            ),
        )
        if record is None:
            return None
        if not isinstance(
            record.value,
            SignedDurableEvidenceEpoch,
        ):
            raise DurableEvidenceEpochError(
                "evidence epoch record has invalid value type"
            )
        item = record.value
        if item.record_id != record_id:
            raise DurableEvidenceEpochError(
                "evidence epoch key/id mismatch"
            )
        self._verify_signature(
            item
        )
        return item

    def _head(
        self,
        epoch_id: str,
    ) -> tuple[
        int,
        DurableEvidenceEpochHead,
    ] | None:
        record = self.backend.get(
            self.namespace,
            self._head_key(epoch_id),
        )
        if record is None:
            return None
        if not isinstance(
            record.value,
            DurableEvidenceEpochHead,
        ):
            raise DurableEvidenceEpochError(
                "evidence epoch head has invalid value type"
            )
        head = record.value
        if head.epoch_id != epoch_id:
            raise DurableEvidenceEpochError(
                "evidence epoch head identity mismatch"
            )
        return record.revision, head

    def latest(
        self,
        epoch_id: str,
    ) -> SignedDurableEvidenceEpoch | None:
        head = self._head(
            epoch_id
        )
        if head is None:
            return None
        _, value = head
        item = self.get(
            value.record_id
        )
        if item is None:
            raise DurableEvidenceEpochError(
                "evidence epoch head references missing record"
            )
        if (
            item.epoch.completed_at
            != value.completed_at
        ):
            raise DurableEvidenceEpochError(
                "evidence epoch head completion time mismatch"
            )
        return item

    @staticmethod
    def _require_group_member_binding(
        group_member,
        workflow,
    ) -> None:
        if (
            group_member.workflow_id
            != workflow.workflow_id
            or group_member.workflow_binding_digest
            != workflow.binding_digest
            or group_member.retention_plan_digest
            != workflow.retention_plan_digest
            or group_member.current_sequence
            != workflow.current_sequence
            or group_member.current_root
            != workflow.current_root
            or group_member.cutoff_sequence
            != workflow.cutoff_sequence
            or group_member.cutoff_root
            != workflow.cutoff_root
            or group_member.archive_id
            != workflow.archive_id
            or group_member.archive_manifest_digest
            != workflow.archive_manifest_digest
            or group_member.certificate_id
            != workflow.certificate_id
            or group_member.authorization_id
            != workflow.authorization_id
            or group_member.pruning_operation_id
            != workflow.pruning_operation_id
            or group_member.pruning_manifest_digest
            != workflow.pruning_manifest_digest
            or group_member.floor_id
            != workflow.floor_id
            or group_member.deleted_items
            != workflow.deleted_items
            or group_member.delete_count
            != workflow.delete_count
        ):
            raise DurableEvidenceEpochConflict(
                "completed group member differs from persisted workflow"
            )

    def _build_member(
        self,
        group_member,
        request: DurableCompactionGroupRequest,
    ) -> DurableEvidenceEpochMember:
        stored = request.operator.current(
            group_member.workflow_id
        )
        if stored is None:
            raise DurableEvidenceEpochConflict(
                "completed group references missing member workflow"
            )
        workflow = stored.workflow
        if (
            workflow.phase
            is not DurableCompactionWorkflowPhase.COMPLETE
        ):
            raise DurableEvidenceEpochConflict(
                "epoch member workflow is not complete"
            )
        self._require_group_member_binding(
            group_member,
            workflow,
        )

        head = request.chain.head()
        if (
            int(head.sequence)
            != workflow.current_sequence
            or str(head.root_hash)
            != workflow.current_root
        ):
            raise DurableEvidenceEpochConflict(
                "epoch member live head differs from completed workflow"
            )

        archive = (
            request.operator.planner
            .archives.require(
                workflow.archive_id
            )
        )
        archive_digest = (
            archive.manifest.manifest.digest
        )
        if (
            archive_digest
            != workflow.archive_manifest_digest
        ):
            raise DurableEvidenceEpochConflict(
                "epoch member archive manifest differs from workflow"
            )

        certificate = (
            request.operator.certificates.get(
                workflow.certificate_id
            )
        )
        if certificate is None:
            raise DurableEvidenceEpochConflict(
                "epoch member certificate is missing"
            )
        certificate_digest = (
            certificate.certificate.digest
        )

        authorization = (
            request.operator.authorizations.get(
                workflow.authorization_id
            )
        )
        if authorization is None:
            raise DurableEvidenceEpochConflict(
                "epoch member pruning authorization is missing"
            )
        authorization_digest = (
            authorization.authorization.digest
        )

        manifest = (
            request.operator.pruning.manifest(
                workflow.pruning_operation_id
            )
        )
        operation = (
            request.operator.pruning.operation(
                workflow.pruning_operation_id
            )
        )
        if (
            manifest is None
            or operation is None
            or manifest.digest
            != workflow.pruning_manifest_digest
            or operation.manifest_digest
            != manifest.digest
            or operation.phase
            is not DurablePruningPhase.COMPLETE
        ):
            raise DurableEvidenceEpochConflict(
                "epoch member pruning state is not complete and bound"
            )

        floor_item = (
            request.operator.pruning
            .hot_floors.floor_at(
                workflow.chain_id,
                workflow.cutoff_sequence,
            )
        )
        if floor_item is None:
            raise DurableEvidenceEpochConflict(
                "epoch member signed hot floor is missing"
            )
        floor = floor_item.floor
        if (
            floor.floor_id
            != workflow.floor_id
            or floor.chain_id
            != workflow.chain_id
            or floor.sequence
            != workflow.cutoff_sequence
            or floor.root_hash
            != workflow.cutoff_root
            or floor.archive_id
            != workflow.archive_id
            or floor.archive_manifest_digest
            != workflow.archive_manifest_digest
            or floor.compaction_certificate_id
            != workflow.certificate_id
            or floor.pruning_authorization_id
            != workflow.authorization_id
            or floor.operation_id
            != workflow.pruning_operation_id
        ):
            raise DurableEvidenceEpochConflict(
                "epoch member signed hot floor differs from workflow authority"
            )

        current_floor = (
            request.chain.hot_floor()
        )
        if (
            current_floor.sequence
            != workflow.cutoff_sequence
            or current_floor.root_hash
            != workflow.cutoff_root
        ):
            raise DurableEvidenceEpochConflict(
                "epoch member current hot floor differs from completed workflow"
            )

        return DurableEvidenceEpochMember(
            workflow.chain_id,
            workflow.workflow_id,
            workflow.digest,
            workflow.binding_digest,
            workflow.retention_plan_digest,
            workflow.current_sequence,
            workflow.current_root,
            workflow.cutoff_sequence,
            workflow.cutoff_root,
            workflow.archive_id,
            workflow.archive_manifest_digest,
            workflow.certificate_id,
            certificate_digest,
            workflow.authorization_id,
            authorization_digest,
            workflow.pruning_operation_id,
            workflow.pruning_manifest_digest,
            workflow.floor_id,
            floor.digest,
            floor.fencing_token,
            workflow.deleted_items,
            workflow.delete_count,
        )

    def _build_epoch(
        self,
        group_id: str,
        requests: Sequence[
            DurableCompactionGroupRequest
        ],
    ) -> DurableEvidenceEpoch:
        stored = self.coordinator.current(
            group_id
        )
        if stored is None:
            raise DurableEvidenceEpochConflict(
                "evidence epoch group is missing"
            )
        group = stored.group
        if (
            group.phase
            is not DurableCompactionGroupPhase.COMPLETE
        ):
            raise DurableEvidenceEpochConflict(
                "evidence epoch requires a completed compaction group"
            )
        request_map = self._request_map(
            requests
        )
        if set(request_map) != {
            member.chain_id
            for member in group.members
        }:
            raise DurableEvidenceEpochConflict(
                "epoch request set differs from completed group"
            )

        members = tuple(
            self._build_member(
                member,
                request_map[
                    member.chain_id
                ],
            )
            for member in group.members
        )
        record_id = (
            DurableEvidenceEpoch
            .derive_record_id(
                epoch_id=group.epoch_id,
                group_id=group.group_id,
                group_digest=group.digest,
                group_binding_digest=(
                    group.binding_digest
                ),
                operator_id=group.operator_id,
                completed_at=group.updated_at,
                members=members,
            )
        )
        return DurableEvidenceEpoch(
            1,
            record_id,
            group.epoch_id,
            group.group_id,
            group.digest,
            group.binding_digest,
            group.operator_id,
            group.updated_at,
            members,
        )

    def _put_immutable(
        self,
        item: SignedDurableEvidenceEpoch,
    ) -> None:
        key = self._record_key(
            item.record_id
        )
        record = self.backend.get(
            self.namespace,
            key,
        )
        if record is None:
            try:
                self.backend.put_if_absent(
                    self.namespace,
                    key,
                    item,
                )
                return
            except DistributedStateConflict:
                record = self.backend.get(
                    self.namespace,
                    key,
                )
                if record is None:
                    raise
        if not isinstance(
            record.value,
            SignedDurableEvidenceEpoch,
        ):
            raise DurableEvidenceEpochError(
                "evidence epoch immutable record has invalid value type"
            )
        if (
            record.value.epoch
            != item.epoch
        ):
            raise DurableEvidenceEpochConflict(
                "evidence epoch record id already binds different epoch content"
            )

    def publish(
        self,
        group_id: str,
        requests: Sequence[
            DurableCompactionGroupRequest
        ],
    ) -> SignedDurableEvidenceEpoch:
        epoch = self._build_epoch(
            group_id,
            requests,
        )
        existing = self.get(
            epoch.record_id
        )
        if existing is not None:
            return existing

        item = self._sign(epoch)
        self._put_immutable(item)

        head_key = self._head_key(
            epoch.epoch_id
        )
        for _ in range(
            self.max_cas_retries
        ):
            current = self._head(
                epoch.epoch_id
            )
            if current is None:
                revision = 0
                generation = 1
            else:
                revision, head = current
                if (
                    head.record_id
                    == epoch.record_id
                ):
                    return item
                previous = self.get(
                    head.record_id
                )
                if previous is None:
                    raise DurableEvidenceEpochError(
                        "evidence epoch latest head references missing record"
                    )
                if (
                    epoch.completed_at
                    <= previous.epoch.completed_at
                ):
                    raise DurableEvidenceEpochConflict(
                        "evidence epoch publication would roll back latest completion"
                    )
                generation = (
                    head.generation + 1
                )
            next_head = DurableEvidenceEpochHead(
                epoch.epoch_id,
                epoch.record_id,
                generation,
                epoch.completed_at,
            )
            try:
                self.backend.compare_and_swap(
                    self.namespace,
                    head_key,
                    expected_revision=revision,
                    value=next_head,
                )
                return item
            except DistributedStateConflict:
                continue
        raise DurableEvidenceEpochError(
            "evidence epoch head CAS retry budget exhausted"
        )

    @staticmethod
    def _historical_head_valid(
        request: DurableCompactionGroupRequest,
        member: DurableEvidenceEpochMember,
    ) -> bool:
        head = request.chain.head()
        if (
            int(head.sequence)
            == member.current_sequence
            and str(head.root_hash)
            == member.current_root
        ):
            return True
        ancestor = getattr(
            request.chain,
            "root_is_ancestor",
            None,
        )
        if callable(ancestor):
            try:
                if ancestor(
                    member.current_root
                ):
                    return True
            except Exception:
                pass
        try:
            return bool(
                request.operator.planner
                .archives.verify_root(
                    member.chain_id,
                    member.current_root,
                )
            )
        except Exception:
            return False

    def _verify_member(
        self,
        member: DurableEvidenceEpochMember,
        request: DurableCompactionGroupRequest,
    ) -> DurableEvidenceEpochMemberVerification:
        reasons: list[str] = []

        workflow_valid = False
        stored = request.operator.current(
            member.workflow_id
        )
        if stored is None:
            reasons.append(
                "member workflow is missing"
            )
        else:
            workflow = stored.workflow
            workflow_valid = (
                workflow.phase
                is DurableCompactionWorkflowPhase.COMPLETE
                and workflow.digest
                == member.workflow_digest
                and workflow.binding_digest
                == member.workflow_binding_digest
                and workflow.retention_plan_digest
                == member.retention_plan_digest
                and workflow.current_sequence
                == member.current_sequence
                and workflow.current_root
                == member.current_root
                and workflow.cutoff_sequence
                == member.cutoff_sequence
                and workflow.cutoff_root
                == member.cutoff_root
                and workflow.archive_id
                == member.archive_id
                and workflow.archive_manifest_digest
                == member.archive_manifest_digest
                and workflow.certificate_id
                == member.certificate_id
                and workflow.authorization_id
                == member.authorization_id
                and workflow.pruning_operation_id
                == member.pruning_operation_id
                and workflow.pruning_manifest_digest
                == member.pruning_manifest_digest
                and workflow.floor_id
                == member.floor_id
            )
            if not workflow_valid:
                reasons.append(
                    "member workflow differs from epoch"
                )

        archive_valid = False
        try:
            archive = (
                request.operator.planner
                .archives.require(
                    member.archive_id
                )
            )
            archive_valid = (
                archive.manifest.manifest.digest
                == member.archive_manifest_digest
            )
        except Exception:
            archive_valid = False
        if not archive_valid:
            reasons.append(
                "member archive is missing or invalid"
            )

        certificate_valid = False
        try:
            certificate = (
                request.operator.certificates.get(
                    member.certificate_id
                )
            )
            certificate_valid = (
                certificate is not None
                and certificate.certificate.digest
                == member.certificate_digest
            )
        except Exception:
            certificate_valid = False
        if not certificate_valid:
            reasons.append(
                "member compaction certificate is missing or invalid"
            )

        authorization_valid = False
        try:
            authorization = (
                request.operator.authorizations.get(
                    member.authorization_id
                )
            )
            authorization_valid = (
                authorization is not None
                and authorization.authorization.digest
                == member.authorization_digest
            )
        except Exception:
            authorization_valid = False
        if not authorization_valid:
            reasons.append(
                "member pruning authorization is missing or invalid"
            )

        pruning_valid = False
        try:
            manifest = (
                request.operator.pruning.manifest(
                    member.pruning_operation_id
                )
            )
            operation = (
                request.operator.pruning.operation(
                    member.pruning_operation_id
                )
            )
            pruning_valid = (
                manifest is not None
                and operation is not None
                and manifest.digest
                == member.pruning_manifest_digest
                and operation.manifest_digest
                == manifest.digest
                and operation.phase
                is DurablePruningPhase.COMPLETE
                and operation.deleted_items
                == member.deleted_items
            )
        except Exception:
            pruning_valid = False
        if not pruning_valid:
            reasons.append(
                "member pruning operation is missing, incomplete, or invalid"
            )

        floor_valid = False
        try:
            floor_item = (
                request.operator.pruning
                .hot_floors.get(
                    member.floor_id
                )
            )
            if floor_item is None:
                floor_item = (
                    request.operator.pruning
                    .hot_floors.floor_at(
                        member.chain_id,
                        member.cutoff_sequence,
                    )
                )
            if floor_item is not None:
                floor = floor_item.floor
                floor_valid = (
                    floor.floor_id
                    == member.floor_id
                    and floor.digest
                    == member.floor_digest
                    and floor.chain_id
                    == member.chain_id
                    and floor.sequence
                    == member.cutoff_sequence
                    and floor.root_hash
                    == member.cutoff_root
                    and floor.archive_id
                    == member.archive_id
                    and floor.archive_manifest_digest
                    == member.archive_manifest_digest
                    and floor.compaction_certificate_id
                    == member.certificate_id
                    and floor.pruning_authorization_id
                    == member.authorization_id
                    and floor.operation_id
                    == member.pruning_operation_id
                    and floor.fencing_token
                    == member.floor_fencing_token
                )
        except Exception:
            floor_valid = False
        if not floor_valid:
            reasons.append(
                "member signed hot floor is missing or invalid"
            )

        live_head_valid = (
            self._historical_head_valid(
                request,
                member,
            )
        )
        if not live_head_valid:
            reasons.append(
                "member completed live head is neither current, hot ancestor, nor archived"
            )

        current_floor = (
            request.chain.hot_floor()
        )
        current_floor_exact = (
            current_floor.sequence
            == member.cutoff_sequence
            and current_floor.root_hash
            == member.cutoff_root
        )

        historically_valid = (
            workflow_valid
            and archive_valid
            and certificate_valid
            and authorization_valid
            and pruning_valid
            and floor_valid
            and live_head_valid
            and not reasons
        )
        if not historically_valid:
            state = (
                DurableEvidenceEpochMemberState.INVALID
            )
        elif current_floor_exact:
            state = (
                DurableEvidenceEpochMemberState.VALID
            )
        else:
            state = (
                DurableEvidenceEpochMemberState.STALE_CURRENT_FLOOR
            )
        return DurableEvidenceEpochMemberVerification(
            member.chain_id,
            state,
            workflow_valid,
            archive_valid,
            certificate_valid,
            authorization_valid,
            pruning_valid,
            floor_valid,
            live_head_valid,
            current_floor_exact,
            tuple(reasons),
        )

    def inspect(
        self,
        record_id: str,
        requests: Sequence[
            DurableCompactionGroupRequest
        ],
    ) -> DurableEvidenceEpochVerification:
        item = self.get(
            record_id
        )
        if item is None:
            raise DurableEvidenceEpochError(
                "evidence epoch record is missing"
            )
        request_map = self._request_map(
            requests
        )
        epoch = item.epoch
        reasons: list[str] = []

        signature_valid = True
        try:
            self._verify_signature(
                item
            )
        except DurableEvidenceEpochError as exc:
            signature_valid = False
            reasons.append(str(exc))

        group_valid = False
        stored_group = (
            self.coordinator.current(
                epoch.group_id
            )
        )
        if stored_group is None:
            reasons.append(
                "completed compaction group is missing"
            )
        else:
            group = stored_group.group
            group_valid = (
                group.phase
                is DurableCompactionGroupPhase.COMPLETE
                and group.digest
                == epoch.group_digest
                and group.binding_digest
                == epoch.group_binding_digest
                and group.epoch_id
                == epoch.epoch_id
                and group.operator_id
                == epoch.operator_id
            )
            if not group_valid:
                reasons.append(
                    "completed compaction group differs from epoch artifact"
                )

        if set(request_map) != {
            member.chain_id
            for member in epoch.members
        }:
            raise DurableEvidenceEpochConflict(
                "epoch verification request set differs from artifact members"
            )

        member_reports = tuple(
            self._verify_member(
                member,
                request_map[
                    member.chain_id
                ],
            )
            for member in epoch.members
        )
        latest = self.latest(
            epoch.epoch_id
        )
        latest_for_epoch = (
            latest is not None
            and latest.record_id
            == epoch.record_id
        )
        return DurableEvidenceEpochVerification(
            item,
            signature_valid,
            group_valid,
            latest_for_epoch,
            member_reports,
            tuple(reasons),
        )

    def require_historically_valid(
        self,
        record_id: str,
        requests: Sequence[
            DurableCompactionGroupRequest
        ],
    ) -> DurableEvidenceEpochVerification:
        report = self.inspect(
            record_id,
            requests,
        )
        if not report.historically_valid:
            detail = (
                report.reasons[0]
                if report.reasons
                else next(
                    (
                        reason
                        for member
                        in report.members
                        for reason
                        in member.reasons
                    ),
                    "evidence epoch historical verification failed",
                )
            )
            raise DurableEvidenceEpochError(
                detail
            )
        return report

    def require_current(
        self,
        epoch_id: str,
        requests: Sequence[
            DurableCompactionGroupRequest
        ],
    ) -> DurableEvidenceEpochVerification:
        item = self.latest(
            epoch_id
        )
        if item is None:
            raise DurableEvidenceEpochError(
                "latest evidence epoch is missing"
            )
        report = self.inspect(
            item.record_id,
            requests,
        )
        if not report.current:
            detail = (
                report.reasons[0]
                if report.reasons
                else next(
                    (
                        reason
                        for member
                        in report.members
                        for reason
                        in member.reasons
                    ),
                    "latest evidence epoch is not current",
                )
            )
            raise DurableEvidenceEpochError(
                detail
            )
        return report
