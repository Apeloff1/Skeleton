"""Signed fenced maintenance epochs for cross-operation durable evidence safety.

Durable compaction, pruning, failover, repair, and migration each have strong
local authority boundaries.  Those local boundaries are insufficient when two
different maintenance classes target the same evidence resources concurrently.

This module adds one conservative cross-operation authority.  An epoch owns a
sorted resource set through backend fencing leases, signs the exact resource
state observed at acquisition, and becomes stale automatically if any lease is
renewed, replaced, released, or expires.  Callers can therefore gate destructive
or topology-changing operations on one shared authority without weakening their
existing certificates, reservations, pruning authorizations, or failover tickets.

The epoch is an additional guard.  It never replaces operation-specific
authorization.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import hashlib
import json
import math
import secrets
import time
from typing import Callable, Iterable, Mapping

from skeleton.shells.ai.distributed_state import (
    DistributedStateConflict,
    FencedLease,
    LeaseConflict,
)
from skeleton.shells.ai.signed_artifact import (
    ArtifactSignatureError,
    ArtifactSigner,
    SignedArtifact,
)
from skeleton.shells.ai.store_protocol import DistributedAIBackend


MAINTENANCE_ARTIFACT_TYPE = "shell-ai-durable-maintenance-epoch"
GENESIS_ROOT = "0" * 64


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
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(
            f"{name} must be 64-character digest"
        ) from exc
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


def _timestamp(name: str, value: float) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0.0
    ):
        raise ValueError(
            f"{name} must be finite and non-negative"
        )
    return float(value)


class DurableMaintenanceOperation(str, Enum):
    COMPACTION = "compaction"
    PRUNING = "pruning"
    FAILOVER = "failover"
    ARCHIVE_REPAIR = "archive_repair"
    CHECKPOINT_REPAIR = "checkpoint_repair"
    INDEX_REPAIR = "index_repair"
    VERIFICATION_REPAIR = "verification_repair"
    SEQUENCE_MIGRATION = "sequence_migration"
    REPLICATION_REPAIR = "replication_repair"
    HOT_FLOOR_REPAIR = "hot_floor_repair"


class DurableMaintenanceState(str, Enum):
    ACTIVE = "active"
    RELEASED = "released"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"
    INVALIDATED = "invalidated"


@dataclass(frozen=True)
class DurableMaintenancePolicy:
    max_resources: int = 32
    default_ttl_seconds: float = 120.0
    max_ttl_seconds: float = 900.0
    max_renewals: int = 16
    require_state_commitments: bool = True

    def __post_init__(self) -> None:
        for name in (
            "max_resources",
            "max_renewals",
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
        for name in (
            "default_ttl_seconds",
            "max_ttl_seconds",
        ):
            value = _timestamp(
                name,
                getattr(self, name),
            )
            if value <= 0.0:
                raise ValueError(
                    f"{name} must be positive"
                )
            object.__setattr__(
                self,
                name,
                value,
            )
        if (
            self.default_ttl_seconds
            > self.max_ttl_seconds
        ):
            raise ValueError(
                "default maintenance TTL exceeds maximum"
            )
        if not isinstance(
            self.require_state_commitments,
            bool,
        ):
            raise ValueError(
                "require_state_commitments must be bool"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "max_resources": self.max_resources,
            "default_ttl_seconds": (
                self.default_ttl_seconds
            ),
            "max_ttl_seconds": self.max_ttl_seconds,
            "max_renewals": self.max_renewals,
            "require_state_commitments": (
                self.require_state_commitments
            ),
        }

    @classmethod
    def from_chain(
        cls,
        chain_id: str,
        chain: object,
        *,
        resource_kind: str = "evidence-chain",
    ) -> "DurableMaintenanceResource":
        chain_id = _identity(
            "chain_id",
            chain_id,
            maximum=256,
        )
        _identity(
            "resource_kind",
            resource_kind,
            maximum=128,
        )
        head_method = getattr(
            chain,
            "head",
            None,
        )
        if not callable(head_method):
            raise TypeError(
                "chain must expose head()"
            )
        head = head_method()
        try:
            sequence = int(
                getattr(head, "sequence")
            )
            root_hash = str(
                getattr(head, "root_hash")
            )
        except Exception as exc:
            raise TypeError(
                "chain head must expose sequence and root_hash"
            ) from exc
        state_raw = json.dumps(
            {
                "chain_id": chain_id,
                "resource_kind": resource_kind,
                "sequence": sequence,
                "root_hash": root_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        state_digest = hashlib.sha256(
            state_raw
        ).hexdigest()
        return cls(
            chain_id,
            resource_kind,
            sequence,
            root_hash,
            state_digest,
        )

    @classmethod
    def replica(
        cls,
        replica_id: str,
        *,
        journal_sequence: int,
        journal_root: str,
        receipt_sequence: int,
        receipt_root: str,
        replication_state_digest: str = "",
    ) -> "DurableMaintenanceResource":
        replica_id = _identity(
            "replica_id",
            replica_id,
            maximum=256,
        )
        for name, value in (
            ("journal_sequence", journal_sequence),
            ("receipt_sequence", receipt_sequence),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ValueError(
                    f"{name} must be non-negative integer"
                )
        journal_root = _digest(
            "journal_root",
            journal_root,
        )
        receipt_root = _digest(
            "receipt_root",
            receipt_root,
        )
        replication_state_digest = _digest(
            "replication_state_digest",
            replication_state_digest,
            optional=True,
        )
        binding = {
            "replica_id": replica_id,
            "journal_sequence": journal_sequence,
            "journal_root": journal_root,
            "receipt_sequence": receipt_sequence,
            "receipt_root": receipt_root,
            "replication_state_digest": (
                replication_state_digest
            ),
        }
        raw = json.dumps(
            binding,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        combined_root = hashlib.sha256(
            raw
        ).hexdigest()
        state_digest = (
            replication_state_digest
            or combined_root
        )
        return cls(
            replica_id,
            "evidence-replica",
            max(
                journal_sequence,
                receipt_sequence,
            ),
            combined_root,
            state_digest,
        )

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class DurableMaintenanceResource:
    resource_id: str
    resource_kind: str
    sequence: int
    root_hash: str
    state_digest: str = ""

    def __post_init__(self) -> None:
        _identity(
            "resource_id",
            self.resource_id,
            maximum=256,
        )
        _identity(
            "resource_kind",
            self.resource_kind,
            maximum=128,
        )
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 0
        ):
            raise ValueError(
                "maintenance resource sequence must be non-negative integer"
            )
        object.__setattr__(
            self,
            "root_hash",
            _digest(
                "root_hash",
                self.root_hash,
            ),
        )
        object.__setattr__(
            self,
            "state_digest",
            _digest(
                "state_digest",
                self.state_digest,
                optional=True,
            ),
        )
        if (
            self.sequence == 0
            and self.root_hash != GENESIS_ROOT
        ):
            raise ValueError(
                "zero-sequence resource must use genesis root"
            )

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "resource_id": self.resource_id,
            "resource_kind": self.resource_kind,
            "sequence": self.sequence,
            "root_hash": self.root_hash,
            "state_digest": self.state_digest,
        }


@dataclass(frozen=True)
class DurableMaintenanceClaim:
    resource_id: str
    lease_namespace: str
    lease_key: str
    lease_owner: str
    fencing_token: int
    acquired_at: float
    expires_at: float

    def __post_init__(self) -> None:
        for name, maximum in (
            ("resource_id", 256),
            ("lease_namespace", 128),
            ("lease_key", 512),
            ("lease_owner", 256),
        ):
            _identity(
                name,
                getattr(self, name),
                maximum=maximum,
            )
        if (
            isinstance(self.fencing_token, bool)
            or not isinstance(self.fencing_token, int)
            or self.fencing_token <= 0
        ):
            raise ValueError(
                "maintenance fencing_token must be positive integer"
            )
        object.__setattr__(
            self,
            "acquired_at",
            _timestamp(
                "acquired_at",
                self.acquired_at,
            ),
        )
        object.__setattr__(
            self,
            "expires_at",
            _timestamp(
                "expires_at",
                self.expires_at,
            ),
        )
        if self.expires_at <= self.acquired_at:
            raise ValueError(
                "maintenance claim expiry must follow acquisition"
            )

    @classmethod
    def from_lease(
        cls,
        resource_id: str,
        lease: FencedLease,
    ) -> "DurableMaintenanceClaim":
        if not isinstance(lease, FencedLease):
            raise TypeError(
                "lease must be FencedLease"
            )
        return cls(
            resource_id,
            lease.namespace,
            lease.key,
            lease.owner,
            lease.fencing_token,
            lease.acquired_at,
            lease.expires_at,
        )

    def lease(self) -> FencedLease:
        return FencedLease(
            self.lease_namespace,
            self.lease_key,
            self.lease_owner,
            self.fencing_token,
            self.acquired_at,
            self.expires_at,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "resource_id": self.resource_id,
            "lease_namespace": self.lease_namespace,
            "lease_key": self.lease_key,
            "lease_owner": self.lease_owner,
            "fencing_token": self.fencing_token,
            "acquired_at": self.acquired_at,
            "expires_at": self.expires_at,
        }


@dataclass(frozen=True)
class DurableMaintenanceEpoch:
    schema_version: int
    epoch_id: str
    operation: DurableMaintenanceOperation
    owner_id: str
    lease_owner: str
    generation: int
    renewal_count: int
    resources: tuple[DurableMaintenanceResource, ...]
    claims: tuple[DurableMaintenanceClaim, ...]
    policy_digest: str
    nonce: str
    issued_at: float
    expires_at: float
    parent_epoch_id: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(
                "unsupported durable maintenance epoch schema"
            )
        object.__setattr__(
            self,
            "epoch_id",
            _digest(
                "epoch_id",
                self.epoch_id,
            ),
        )
        object.__setattr__(
            self,
            "operation",
            DurableMaintenanceOperation(
                self.operation
            ),
        )
        _identity(
            "owner_id",
            self.owner_id,
            maximum=256,
        )
        _identity(
            "lease_owner",
            self.lease_owner,
            maximum=256,
        )
        for name in (
            "generation",
            "renewal_count",
        ):
            value = getattr(self, name)
            minimum = 1 if name == "generation" else 0
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < minimum
            ):
                raise ValueError(
                    f"invalid maintenance {name}"
                )
        resources = tuple(self.resources)
        claims = tuple(self.claims)
        if not resources:
            raise ValueError(
                "maintenance epoch requires resources"
            )
        if len(resources) != len(claims):
            raise ValueError(
                "maintenance resource/claim count mismatch"
            )
        resource_ids = tuple(
            item.resource_id
            for item in resources
        )
        claim_ids = tuple(
            item.resource_id
            for item in claims
        )
        if resource_ids != tuple(
            sorted(resource_ids)
        ):
            raise ValueError(
                "maintenance resources must be sorted"
            )
        if claim_ids != resource_ids:
            raise ValueError(
                "maintenance claims must align with resources"
            )
        if len(set(resource_ids)) != len(resource_ids):
            raise ValueError(
                "maintenance resources must be unique"
            )
        if any(
            claim.lease_owner != self.lease_owner
            for claim in claims
        ):
            raise ValueError(
                "maintenance claim lease_owner mismatch"
            )
        object.__setattr__(
            self,
            "resources",
            resources,
        )
        object.__setattr__(
            self,
            "claims",
            claims,
        )
        object.__setattr__(
            self,
            "policy_digest",
            _digest(
                "policy_digest",
                self.policy_digest,
            ),
        )
        _identity(
            "nonce",
            self.nonce,
            maximum=256,
        )
        object.__setattr__(
            self,
            "issued_at",
            _timestamp(
                "issued_at",
                self.issued_at,
            ),
        )
        object.__setattr__(
            self,
            "expires_at",
            _timestamp(
                "expires_at",
                self.expires_at,
            ),
        )
        if self.expires_at <= self.issued_at:
            raise ValueError(
                "maintenance epoch expiry must follow issue time"
            )
        object.__setattr__(
            self,
            "parent_epoch_id",
            _digest(
                "parent_epoch_id",
                self.parent_epoch_id,
                optional=True,
            ),
        )
        if self.renewal_count == 0 and self.parent_epoch_id:
            raise ValueError(
                "initial maintenance epoch may not have parent"
            )
        if self.renewal_count > 0 and not self.parent_epoch_id:
            raise ValueError(
                "renewed maintenance epoch requires parent"
            )

    @staticmethod
    def derive_id(
        *,
        operation: DurableMaintenanceOperation,
        owner_id: str,
        lease_owner: str,
        generation: int,
        renewal_count: int,
        resources: tuple[DurableMaintenanceResource, ...],
        claims: tuple[DurableMaintenanceClaim, ...],
        policy_digest: str,
        nonce: str,
        issued_at: float,
        expires_at: float,
        parent_epoch_id: str = "",
    ) -> str:
        raw = json.dumps(
            {
                "authority": (
                    "durable-maintenance-epoch"
                ),
                "operation": (
                    DurableMaintenanceOperation(
                        operation
                    ).value
                ),
                "owner_id": owner_id,
                "lease_owner": lease_owner,
                "generation": generation,
                "renewal_count": renewal_count,
                "resources": [
                    item.to_dict()
                    for item in resources
                ],
                "claims": [
                    item.to_dict()
                    for item in claims
                ],
                "policy_digest": policy_digest,
                "nonce": nonce,
                "issued_at": float(issued_at),
                "expires_at": float(expires_at),
                "parent_epoch_id": parent_epoch_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    @property
    def resource_ids(self) -> tuple[str, ...]:
        return tuple(
            item.resource_id
            for item in self.resources
        )

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.unsigned_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def unsigned_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "epoch_id": self.epoch_id,
            "operation": self.operation.value,
            "owner_id": self.owner_id,
            "lease_owner": self.lease_owner,
            "generation": self.generation,
            "renewal_count": self.renewal_count,
            "resources": [
                item.to_dict()
                for item in self.resources
            ],
            "claims": [
                item.to_dict()
                for item in self.claims
            ],
            "policy_digest": self.policy_digest,
            "nonce": self.nonce,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "parent_epoch_id": self.parent_epoch_id,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            **self.unsigned_dict(),
            "digest": self.digest,
        }


@dataclass(frozen=True)
class SignedDurableMaintenanceEpoch:
    epoch: DurableMaintenanceEpoch
    signature: SignedArtifact

    def __post_init__(self) -> None:
        if not isinstance(
            self.epoch,
            DurableMaintenanceEpoch,
        ):
            raise TypeError(
                "epoch must be DurableMaintenanceEpoch"
            )
        if not isinstance(
            self.signature,
            SignedArtifact,
        ):
            raise TypeError(
                "signature must be SignedArtifact"
            )
        if (
            self.signature.artifact_type
            != MAINTENANCE_ARTIFACT_TYPE
        ):
            raise ValueError(
                "maintenance signature artifact type mismatch"
            )
        if (
            self.signature.artifact_digest
            != self.epoch.digest
        ):
            raise ValueError(
                "maintenance signature digest mismatch"
            )

    @property
    def epoch_id(self) -> str:
        return self.epoch.epoch_id

    def to_dict(self) -> dict[str, object]:
        return {
            "epoch": self.epoch.to_dict(),
            "signature": self.signature.to_dict(),
        }


@dataclass(frozen=True)
class DurableMaintenanceRecord:
    epoch_id: str
    epoch_digest: str
    operation: DurableMaintenanceOperation
    owner_id: str
    generation: int
    state: DurableMaintenanceState
    created_at: float
    updated_at: float
    released_at: float = 0.0
    replacement_epoch_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "epoch_id",
            _digest(
                "epoch_id",
                self.epoch_id,
            ),
        )
        object.__setattr__(
            self,
            "epoch_digest",
            _digest(
                "epoch_digest",
                self.epoch_digest,
            ),
        )
        object.__setattr__(
            self,
            "operation",
            DurableMaintenanceOperation(
                self.operation
            ),
        )
        _identity(
            "owner_id",
            self.owner_id,
            maximum=256,
        )
        if (
            isinstance(self.generation, bool)
            or not isinstance(self.generation, int)
            or self.generation <= 0
        ):
            raise ValueError(
                "maintenance generation must be positive"
            )
        object.__setattr__(
            self,
            "state",
            DurableMaintenanceState(
                self.state
            ),
        )
        object.__setattr__(
            self,
            "created_at",
            _timestamp(
                "created_at",
                self.created_at,
            ),
        )
        object.__setattr__(
            self,
            "updated_at",
            _timestamp(
                "updated_at",
                self.updated_at,
            ),
        )
        object.__setattr__(
            self,
            "released_at",
            _timestamp(
                "released_at",
                self.released_at,
            ),
        )
        if self.updated_at < self.created_at:
            raise ValueError(
                "maintenance record updated_at precedes creation"
            )
        if (
            self.state
            is DurableMaintenanceState.RELEASED
            and self.released_at <= 0.0
        ):
            raise ValueError(
                "released maintenance record requires released_at"
            )
        object.__setattr__(
            self,
            "replacement_epoch_id",
            _digest(
                "replacement_epoch_id",
                self.replacement_epoch_id,
                optional=True,
            ),
        )
        if (
            self.state
            is DurableMaintenanceState.SUPERSEDED
            and not self.replacement_epoch_id
        ):
            raise ValueError(
                "superseded maintenance record requires replacement"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "epoch_id": self.epoch_id,
            "epoch_digest": self.epoch_digest,
            "operation": self.operation.value,
            "owner_id": self.owner_id,
            "generation": self.generation,
            "state": self.state.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "released_at": self.released_at,
            "replacement_epoch_id": (
                self.replacement_epoch_id
            ),
        }


@dataclass(frozen=True)
class StoredDurableMaintenanceEpoch:
    revision: int
    signed: SignedDurableMaintenanceEpoch
    record: DurableMaintenanceRecord

    def __post_init__(self) -> None:
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision <= 0
        ):
            raise ValueError(
                "maintenance revision must be positive"
            )


@dataclass(frozen=True)
class DurableMaintenanceStatus:
    signed: SignedDurableMaintenanceEpoch
    record: DurableMaintenanceRecord
    signature_valid: bool
    leases_valid: bool
    time_valid: bool
    policy_valid: bool
    operation_valid: bool
    resources_valid: bool
    live_state_valid: bool
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (
            "signature_valid",
            "leases_valid",
            "time_valid",
            "policy_valid",
            "operation_valid",
            "resources_valid",
            "live_state_valid",
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
    def active(self) -> bool:
        return (
            self.record.state
            is DurableMaintenanceState.ACTIVE
            and self.signature_valid
            and self.leases_valid
            and self.time_valid
            and self.policy_valid
            and self.operation_valid
            and self.resources_valid
            and self.live_state_valid
            and not self.reasons
        )

    @property
    def destructive_action_authorized(self) -> bool:
        return self.active

    def to_dict(self) -> dict[str, object]:
        return {
            "epoch": self.signed.to_dict(),
            "record": self.record.to_dict(),
            "signature_valid": self.signature_valid,
            "leases_valid": self.leases_valid,
            "time_valid": self.time_valid,
            "policy_valid": self.policy_valid,
            "operation_valid": self.operation_valid,
            "resources_valid": self.resources_valid,
            "live_state_valid": self.live_state_valid,
            "active": self.active,
            "destructive_action_authorized": (
                self.destructive_action_authorized
            ),
            "reasons": list(self.reasons),
        }


class DurableMaintenanceError(RuntimeError):
    pass


class DurableMaintenanceConflict(
    DurableMaintenanceError
):
    pass


class DurableMaintenanceStale(
    DurableMaintenanceError
):
    pass


class DurableMaintenanceStore:
    """Issue, renew, verify, and release signed fenced maintenance epochs."""

    def __init__(
        self,
        backend: DistributedAIBackend,
        signer: ArtifactSigner,
        *,
        policy: DurableMaintenancePolicy | None = None,
        namespace: str = "shell-ai-durable-maintenance",
        max_cas_retries: int = 32,
        clock: Callable[[], float] = time.monotonic,
        nonce_factory: Callable[[], str] = (
            lambda: secrets.token_hex(16)
        ),
    ) -> None:
        if not isinstance(
            backend,
            DistributedAIBackend,
        ):
            raise TypeError(
                "backend must satisfy DistributedAIBackend"
            )
        if not isinstance(
            signer,
            ArtifactSigner,
        ):
            raise TypeError(
                "signer must be ArtifactSigner"
            )
        if not namespace or len(namespace) > 128:
            raise ValueError(
                "invalid maintenance namespace"
            )
        if (
            isinstance(max_cas_retries, bool)
            or not isinstance(max_cas_retries, int)
            or not 1 <= max_cas_retries <= 128
        ):
            raise ValueError(
                "max_cas_retries outside supported range"
            )
        if not callable(clock):
            raise TypeError(
                "clock must be callable"
            )
        if not callable(nonce_factory):
            raise TypeError(
                "nonce_factory must be callable"
            )
        self.backend = backend
        self.signer = signer
        self.policy = (
            policy or DurableMaintenancePolicy()
        )
        self.namespace = namespace
        self.max_cas_retries = max_cas_retries
        self._clock = clock
        self._nonce_factory = nonce_factory

    @property
    def lease_namespace(self) -> str:
        value = self.namespace + "-leases"
        if len(value) > 128:
            return self.namespace[:121] + "-lease"
        return value

    @staticmethod
    def _epoch_key(epoch_id: str) -> str:
        return "epoch:" + _digest(
            "epoch_id",
            epoch_id,
        )

    @staticmethod
    def _record_key(epoch_id: str) -> str:
        return "record:" + _digest(
            "epoch_id",
            epoch_id,
        )

    @staticmethod
    def _resource_key(resource_id: str) -> str:
        _identity(
            "resource_id",
            resource_id,
            maximum=256,
        )
        return "resource:" + hashlib.sha256(
            resource_id.encode()
        ).hexdigest()

    def _now(self) -> float:
        value = self._clock()
        return _timestamp(
            "maintenance clock",
            value,
        )

    def _ttl(
        self,
        ttl_seconds: float | None,
    ) -> float:
        ttl = (
            self.policy.default_ttl_seconds
            if ttl_seconds is None
            else ttl_seconds
        )
        if (
            isinstance(ttl, bool)
            or not isinstance(ttl, (int, float))
            or not math.isfinite(float(ttl))
            or float(ttl) <= 0.0
            or float(ttl)
            > self.policy.max_ttl_seconds
        ):
            raise ValueError(
                "maintenance TTL outside supported range"
            )
        return float(ttl)

    def _resources(
        self,
        resources: Iterable[DurableMaintenanceResource],
    ) -> tuple[DurableMaintenanceResource, ...]:
        items = tuple(resources)
        if not items:
            raise ValueError(
                "maintenance resources are required"
            )
        if len(items) > self.policy.max_resources:
            raise ValueError(
                "maintenance resource count exceeds policy"
            )
        for item in items:
            if not isinstance(
                item,
                DurableMaintenanceResource,
            ):
                raise TypeError(
                    "resources must contain DurableMaintenanceResource"
                )
            if (
                self.policy.require_state_commitments
                and not item.state_digest
            ):
                raise ValueError(
                    "maintenance policy requires resource state_digest"
                )
        items = tuple(
            sorted(
                items,
                key=lambda item: item.resource_id,
            )
        )
        ids = tuple(
            item.resource_id
            for item in items
        )
        if len(ids) != len(set(ids)):
            raise ValueError(
                "maintenance resources must be unique"
            )
        return items

    def _sign(
        self,
        epoch: DurableMaintenanceEpoch,
    ) -> SignedDurableMaintenanceEpoch:
        signature = self.signer.sign(
            MAINTENANCE_ARTIFACT_TYPE,
            epoch.digest,
            metadata={
                "epoch_id": epoch.epoch_id,
                "operation": epoch.operation.value,
                "owner_id": epoch.owner_id,
                "generation": str(
                    epoch.generation
                ),
                "policy_digest": (
                    epoch.policy_digest
                ),
            },
        )
        return SignedDurableMaintenanceEpoch(
            epoch,
            signature,
        )

    def _verify_signature(
        self,
        signed: SignedDurableMaintenanceEpoch,
    ) -> None:
        if not isinstance(
            signed,
            SignedDurableMaintenanceEpoch,
        ):
            raise TypeError(
                "signed must be SignedDurableMaintenanceEpoch"
            )
        try:
            self.signer.verify(
                signed.signature
            )
        except ArtifactSignatureError as exc:
            raise DurableMaintenanceStale(
                "maintenance epoch signature verification failed"
            ) from exc
        if (
            signed.signature.artifact_digest
            != signed.epoch.digest
        ):
            raise DurableMaintenanceStale(
                "maintenance epoch signature digest mismatch"
            )

    def _put_epoch(
        self,
        signed: SignedDurableMaintenanceEpoch,
    ) -> None:
        key = self._epoch_key(
            signed.epoch_id
        )
        try:
            self.backend.put_if_absent(
                self.namespace,
                key,
                signed,
            )
            return
        except DistributedStateConflict:
            existing = self.backend.get(
                self.namespace,
                key,
            )
            if existing is None:
                raise
            if not isinstance(
                existing.value,
                SignedDurableMaintenanceEpoch,
            ):
                raise DurableMaintenanceConflict(
                    "maintenance epoch key has invalid type"
                )
            if existing.value != signed:
                raise DurableMaintenanceConflict(
                    "maintenance epoch id collision"
                )

    def _put_record(
        self,
        record: DurableMaintenanceRecord,
    ) -> int:
        stored = self.backend.put_if_absent(
            self.namespace,
            self._record_key(
                record.epoch_id
            ),
            record,
        )
        return stored.revision

    def _record(
        self,
        epoch_id: str,
    ):
        record = self.backend.get(
            self.namespace,
            self._record_key(
                epoch_id
            ),
        )
        if record is None:
            return None
        if not isinstance(
            record.value,
            DurableMaintenanceRecord,
        ):
            raise DurableMaintenanceConflict(
                "maintenance record has invalid type"
            )
        return record

    def get(
        self,
        epoch_id: str,
    ) -> StoredDurableMaintenanceEpoch | None:
        epoch_record = self.backend.get(
            self.namespace,
            self._epoch_key(
                epoch_id
            ),
        )
        state_record = self._record(
            epoch_id
        )
        if (
            epoch_record is None
            and state_record is None
        ):
            return None
        if (
            epoch_record is None
            or state_record is None
        ):
            raise DurableMaintenanceConflict(
                "maintenance epoch/state is partially missing"
            )
        if not isinstance(
            epoch_record.value,
            SignedDurableMaintenanceEpoch,
        ):
            raise DurableMaintenanceConflict(
                "maintenance epoch value has invalid type"
            )
        signed = epoch_record.value
        record = state_record.value
        if (
            signed.epoch.digest
            != record.epoch_digest
        ):
            raise DurableMaintenanceConflict(
                "maintenance record digest differs from epoch"
            )
        return StoredDurableMaintenanceEpoch(
            state_record.revision,
            signed,
            record,
        )

    def _acquire_claims(
        self,
        resources: tuple[
            DurableMaintenanceResource,
            ...,
        ],
        *,
        lease_owner: str,
        ttl_seconds: float,
    ) -> tuple[DurableMaintenanceClaim, ...]:
        acquired: list[
            DurableMaintenanceClaim
        ] = []
        try:
            for resource in resources:
                lease = self.backend.acquire_lease(
                    self.lease_namespace,
                    self._resource_key(
                        resource.resource_id
                    ),
                    owner=lease_owner,
                    ttl_seconds=ttl_seconds,
                )
                acquired.append(
                    DurableMaintenanceClaim.from_lease(
                        resource.resource_id,
                        lease,
                    )
                )
        except Exception:
            for claim in reversed(acquired):
                try:
                    self.backend.release_lease(
                        claim.lease()
                    )
                except Exception:
                    pass
            raise
        return tuple(acquired)

    def acquire(
        self,
        operation: DurableMaintenanceOperation,
        *,
        owner_id: str,
        resources: Iterable[
            DurableMaintenanceResource
        ],
        ttl_seconds: float | None = None,
    ) -> SignedDurableMaintenanceEpoch:
        operation = DurableMaintenanceOperation(
            operation
        )
        owner_id = _identity(
            "owner_id",
            owner_id,
            maximum=256,
        )
        items = self._resources(
            resources
        )
        ttl = self._ttl(
            ttl_seconds
        )
        now = self._now()
        nonce = str(
            self._nonce_factory()
        )
        _identity(
            "nonce",
            nonce,
            maximum=256,
        )
        lease_owner = (
            f"maintenance:{owner_id}:{nonce}"
        )
        if len(lease_owner) > 256:
            lease_owner = (
                "maintenance:"
                + hashlib.sha256(
                    lease_owner.encode()
                ).hexdigest()
            )
        try:
            claims = self._acquire_claims(
                items,
                lease_owner=lease_owner,
                ttl_seconds=ttl,
            )
        except LeaseConflict as exc:
            raise DurableMaintenanceConflict(
                "maintenance resource already has active authority"
            ) from exc
        expires_at = min(
            claim.expires_at
            for claim in claims
        )
        generation = max(
            claim.fencing_token
            for claim in claims
        )
        epoch_id = DurableMaintenanceEpoch.derive_id(
            operation=operation,
            owner_id=owner_id,
            lease_owner=lease_owner,
            generation=generation,
            renewal_count=0,
            resources=items,
            claims=claims,
            policy_digest=self.policy.digest,
            nonce=nonce,
            issued_at=now,
            expires_at=expires_at,
        )
        epoch = DurableMaintenanceEpoch(
            1,
            epoch_id,
            operation,
            owner_id,
            lease_owner,
            generation,
            0,
            items,
            claims,
            self.policy.digest,
            nonce,
            now,
            expires_at,
        )
        signed = self._sign(
            epoch
        )
        try:
            self._put_epoch(
                signed
            )
            self._put_record(
                DurableMaintenanceRecord(
                    epoch.epoch_id,
                    epoch.digest,
                    epoch.operation,
                    epoch.owner_id,
                    epoch.generation,
                    DurableMaintenanceState.ACTIVE,
                    now,
                    now,
                )
            )
        except Exception:
            for claim in reversed(claims):
                try:
                    self.backend.release_lease(
                        claim.lease()
                    )
                except Exception:
                    pass
            raise
        return signed

    @staticmethod
    def _resource_map(
        resources: Iterable[
            DurableMaintenanceResource
        ],
    ) -> dict[str, DurableMaintenanceResource]:
        result: dict[
            str,
            DurableMaintenanceResource,
        ] = {}
        for item in resources:
            if not isinstance(
                item,
                DurableMaintenanceResource,
            ):
                raise TypeError(
                    "live_resources must contain DurableMaintenanceResource"
                )
            if item.resource_id in result:
                raise ValueError(
                    "duplicate live maintenance resource"
                )
            result[
                item.resource_id
            ] = item
        return result

    def inspect(
        self,
        signed: SignedDurableMaintenanceEpoch,
        *,
        operation: DurableMaintenanceOperation | None = None,
        required_resources: Iterable[str] = (),
        live_resources: Iterable[
            DurableMaintenanceResource
        ] = (),
        enforce_time: bool = True,
    ) -> DurableMaintenanceStatus:
        reasons: list[str] = []
        signature_valid = True
        try:
            self._verify_signature(
                signed
            )
        except Exception as exc:
            signature_valid = False
            reasons.append(
                "signature:"
                + type(exc).__name__
            )
        epoch = signed.epoch
        stored = self.get(
            epoch.epoch_id
        )
        if stored is None:
            record = DurableMaintenanceRecord(
                epoch.epoch_id,
                epoch.digest,
                epoch.operation,
                epoch.owner_id,
                epoch.generation,
                DurableMaintenanceState.EXPIRED,
                epoch.issued_at,
                epoch.issued_at,
            )
            reasons.append(
                "maintenance epoch is not persisted"
            )
        else:
            record = stored.record

        policy_valid = (
            epoch.policy_digest
            == self.policy.digest
        )
        if not policy_valid:
            reasons.append(
                "maintenance policy digest changed"
            )

        operation_valid = True
        if operation is not None:
            operation_valid = (
                epoch.operation
                is DurableMaintenanceOperation(
                    operation
                )
            )
            if not operation_valid:
                reasons.append(
                    "maintenance operation differs"
                )

        required = tuple(
            sorted(
                {
                    _identity(
                        "required_resource",
                        item,
                        maximum=256,
                    )
                    for item in required_resources
                }
            )
        )
        resources_valid = set(required).issubset(
            set(epoch.resource_ids)
        )
        if not resources_valid:
            reasons.append(
                "maintenance epoch lacks required resources"
            )

        now = self._now()
        time_valid = (
            (not enforce_time)
            or now < epoch.expires_at
        )
        if not time_valid:
            reasons.append(
                "maintenance epoch expired"
            )

        leases_valid = True
        for claim in epoch.claims:
            try:
                self.backend.require_fence(
                    claim.lease()
                )
            except Exception:
                leases_valid = False
                reasons.append(
                    "maintenance fence is stale for "
                    + claim.resource_id
                )

        live_state_valid = True
        live = self._resource_map(
            live_resources
        )
        for resource in epoch.resources:
            current = live.get(
                resource.resource_id
            )
            if current is None:
                continue
            if current != resource:
                live_state_valid = False
                reasons.append(
                    "maintenance resource state changed: "
                    + resource.resource_id
                )

        if (
            record.state
            is not DurableMaintenanceState.ACTIVE
        ):
            reasons.append(
                "maintenance record is "
                + record.state.value
            )

        return DurableMaintenanceStatus(
            signed,
            record,
            signature_valid,
            leases_valid,
            time_valid,
            policy_valid,
            operation_valid,
            resources_valid,
            live_state_valid,
            tuple(reasons),
        )

    def require_active(
        self,
        signed: SignedDurableMaintenanceEpoch,
        *,
        operation: DurableMaintenanceOperation | None = None,
        required_resources: Iterable[str] = (),
        live_resources: Iterable[
            DurableMaintenanceResource
        ] = (),
    ) -> DurableMaintenanceStatus:
        status = self.inspect(
            signed,
            operation=operation,
            required_resources=(
                required_resources
            ),
            live_resources=(
                live_resources
            ),
            enforce_time=True,
        )
        if not status.active:
            detail = (
                status.reasons[0]
                if status.reasons
                else "maintenance epoch is inactive"
            )
            raise DurableMaintenanceStale(
                detail
            )
        return status

    def _invalidate_record(
        self,
        epoch_id: str,
    ) -> DurableMaintenanceRecord | None:
        record = self._record(
            epoch_id
        )
        if record is None:
            return None
        if (
            record.value.state
            is not DurableMaintenanceState.ACTIVE
        ):
            return record.value
        now = self._now()
        updated = replace(
            record.value,
            state=DurableMaintenanceState.INVALIDATED,
            updated_at=now,
        )
        try:
            stored = self.backend.compare_and_swap(
                self.namespace,
                self._record_key(
                    epoch_id
                ),
                expected_revision=record.revision,
                value=updated,
            )
            return stored.value
        except DistributedStateConflict:
            current = self._record(
                epoch_id
            )
            return (
                None
                if current is None
                else current.value
            )

    @staticmethod
    def _release_claims_best_effort(
        backend: DistributedAIBackend,
        claims: Iterable[
            DurableMaintenanceClaim
        ],
    ) -> None:
        for claim in reversed(
            tuple(claims)
        ):
            try:
                backend.release_lease(
                    claim.lease()
                )
            except Exception:
                pass

    def renew(
        self,
        signed: SignedDurableMaintenanceEpoch,
        *,
        ttl_seconds: float | None = None,
        live_resources: Iterable[
            DurableMaintenanceResource
        ] = (),
    ) -> SignedDurableMaintenanceEpoch:
        current_status = self.require_active(
            signed,
            live_resources=live_resources,
        )
        epoch = current_status.signed.epoch
        if (
            epoch.renewal_count
            >= self.policy.max_renewals
        ):
            raise DurableMaintenanceConflict(
                "maintenance renewal limit reached"
            )
        ttl = self._ttl(
            ttl_seconds
        )
        now = self._now()
        renewed_claims: list[
            DurableMaintenanceClaim
        ] = []
        renewed_ids: set[str] = set()
        try:
            for claim in epoch.claims:
                renewed = self.backend.renew_lease(
                    claim.lease(),
                    ttl_seconds=ttl,
                )
                renewed_claims.append(
                    DurableMaintenanceClaim.from_lease(
                        claim.resource_id,
                        renewed,
                    )
                )
                renewed_ids.add(
                    claim.resource_id
                )
        except Exception as exc:
            # Renewal is a saga, not an atomic backend primitive.  Once even
            # one claim has been renewed the old epoch is intentionally made
            # unusable.  Release both renewed and still-old claims so a
            # partial renewal cannot strand split authority across resources.
            self._release_claims_best_effort(
                self.backend,
                renewed_claims,
            )
            self._release_claims_best_effort(
                self.backend,
                (
                    claim
                    for claim in epoch.claims
                    if claim.resource_id
                    not in renewed_ids
                ),
            )
            self._invalidate_record(
                epoch.epoch_id
            )
            raise DurableMaintenanceStale(
                "maintenance lease renewal failed and epoch was invalidated"
            ) from exc

        claims = tuple(
            renewed_claims
        )
        expires_at = min(
            claim.expires_at
            for claim in claims
        )
        nonce = str(
            self._nonce_factory()
        )
        _identity(
            "nonce",
            nonce,
            maximum=256,
        )
        next_id = DurableMaintenanceEpoch.derive_id(
            operation=epoch.operation,
            owner_id=epoch.owner_id,
            lease_owner=epoch.lease_owner,
            generation=epoch.generation,
            renewal_count=(
                epoch.renewal_count + 1
            ),
            resources=epoch.resources,
            claims=claims,
            policy_digest=self.policy.digest,
            nonce=nonce,
            issued_at=now,
            expires_at=expires_at,
            parent_epoch_id=epoch.epoch_id,
        )
        next_epoch = DurableMaintenanceEpoch(
            1,
            next_id,
            epoch.operation,
            epoch.owner_id,
            epoch.lease_owner,
            epoch.generation,
            epoch.renewal_count + 1,
            epoch.resources,
            claims,
            self.policy.digest,
            nonce,
            now,
            expires_at,
            epoch.epoch_id,
        )
        next_signed = self._sign(
            next_epoch
        )
        next_persisted = False
        try:
            self._put_epoch(
                next_signed
            )
            self._put_record(
                DurableMaintenanceRecord(
                    next_epoch.epoch_id,
                    next_epoch.digest,
                    next_epoch.operation,
                    next_epoch.owner_id,
                    next_epoch.generation,
                    DurableMaintenanceState.ACTIVE,
                    now,
                    now,
                )
            )
            next_persisted = True

            old_record = self._record(
                epoch.epoch_id
            )
            if old_record is None:
                raise DurableMaintenanceConflict(
                    "maintenance parent record disappeared during renewal"
                )
            if (
                old_record.value.state
                is not DurableMaintenanceState.ACTIVE
            ):
                raise DurableMaintenanceConflict(
                    "maintenance parent is no longer active"
                )
            self.backend.compare_and_swap(
                self.namespace,
                self._record_key(
                    epoch.epoch_id
                ),
                expected_revision=(
                    old_record.revision
                ),
                value=replace(
                    old_record.value,
                    state=DurableMaintenanceState.SUPERSEDED,
                    updated_at=now,
                    replacement_epoch_id=(
                        next_epoch.epoch_id
                    ),
                ),
            )
        except Exception as exc:
            self._release_claims_best_effort(
                self.backend,
                claims,
            )
            self._invalidate_record(
                epoch.epoch_id
            )
            if next_persisted:
                self._invalidate_record(
                    next_epoch.epoch_id
                )
            raise DurableMaintenanceConflict(
                "maintenance renewal commit failed and authority was invalidated"
            ) from exc
        return next_signed

    def release(
        self,
        signed: SignedDurableMaintenanceEpoch,
        *,
        owner_id: str = "",
    ) -> DurableMaintenanceRecord:
        self._verify_signature(
            signed
        )
        epoch = signed.epoch
        if owner_id and (
            _identity(
                "owner_id",
                owner_id,
                maximum=256,
            )
            != epoch.owner_id
        ):
            raise DurableMaintenanceConflict(
                "maintenance release owner mismatch"
            )
        record = self._record(
            epoch.epoch_id
        )
        if record is None:
            raise DurableMaintenanceConflict(
                "maintenance record is missing"
            )
        if (
            record.value.state
            is DurableMaintenanceState.RELEASED
        ):
            return record.value
        if (
            record.value.state
            is DurableMaintenanceState.SUPERSEDED
        ):
            raise DurableMaintenanceConflict(
                "superseded maintenance epoch cannot release renewed leases"
            )

        released_all = True
        for claim in reversed(
            epoch.claims
        ):
            try:
                released = self.backend.release_lease(
                    claim.lease()
                )
                released_all = (
                    released_all
                    and bool(released)
                )
            except LeaseConflict:
                released_all = False
        if not released_all:
            raise DurableMaintenanceStale(
                "one or more maintenance leases are stale"
            )
        now = self._now()
        updated = replace(
            record.value,
            state=DurableMaintenanceState.RELEASED,
            updated_at=now,
            released_at=now,
        )
        try:
            stored = self.backend.compare_and_swap(
                self.namespace,
                self._record_key(
                    epoch.epoch_id
                ),
                expected_revision=record.revision,
                value=updated,
            )
        except DistributedStateConflict as exc:
            current = self._record(
                epoch.epoch_id
            )
            if (
                current is not None
                and current.value.state
                is DurableMaintenanceState.RELEASED
            ):
                return current.value
            raise DurableMaintenanceConflict(
                "maintenance release record conflicted"
            ) from exc
        return stored.value

    def mark_expired(
        self,
        signed: SignedDurableMaintenanceEpoch,
    ) -> DurableMaintenanceRecord:
        self._verify_signature(
            signed
        )
        epoch = signed.epoch
        if self._now() < epoch.expires_at:
            raise DurableMaintenanceConflict(
                "maintenance epoch has not expired"
            )
        record = self._record(
            epoch.epoch_id
        )
        if record is None:
            raise DurableMaintenanceConflict(
                "maintenance record is missing"
            )
        if (
            record.value.state
            is not DurableMaintenanceState.ACTIVE
        ):
            return record.value
        now = self._now()
        updated = replace(
            record.value,
            state=DurableMaintenanceState.EXPIRED,
            updated_at=now,
        )
        try:
            stored = self.backend.compare_and_swap(
                self.namespace,
                self._record_key(
                    epoch.epoch_id
                ),
                expected_revision=record.revision,
                value=updated,
            )
            return stored.value
        except DistributedStateConflict:
            current = self._record(
                epoch.epoch_id
            )
            if current is None:
                raise DurableMaintenanceConflict(
                    "maintenance record disappeared"
                )
            return current.value

    def active_for_resource(
        self,
        resource_id: str,
    ) -> bool:
        resource_id = _identity(
            "resource_id",
            resource_id,
            maximum=256,
        )
        key = self._resource_key(
            resource_id
        )
        try:
            lease = self.backend.acquire_lease(
                self.lease_namespace,
                key,
                owner=(
                    "maintenance-probe:"
                    + secrets.token_hex(8)
                ),
                ttl_seconds=0.001,
            )
        except LeaseConflict:
            return True
        except Exception:
            return True
        try:
            self.backend.release_lease(
                lease
            )
        except Exception:
            # If a supposedly free resource cannot release the probe, treat
            # availability as unknown/busy rather than fail open.
            return True
        return False

    def assert_available(
        self,
        resources: Iterable[str],
        *,
        owner_id: str = "maintenance-probe",
    ) -> None:
        acquired: list[FencedLease] = []
        try:
            for resource_id in sorted(
                {
                    _identity(
                        "resource_id",
                        item,
                        maximum=256,
                    )
                    for item in resources
                }
            ):
                lease = self.backend.acquire_lease(
                    self.lease_namespace,
                    self._resource_key(
                        resource_id
                    ),
                    owner=owner_id,
                    ttl_seconds=0.001,
                )
                acquired.append(
                    lease
                )
        except LeaseConflict as exc:
            raise DurableMaintenanceConflict(
                "maintenance resource is currently reserved"
            ) from exc
        finally:
            for lease in reversed(acquired):
                try:
                    self.backend.release_lease(
                        lease
                    )
                except Exception:
                    pass


class DurableMaintenanceGuard:
    """Small adapter for optional fail-closed integration in other operators."""

    def __init__(
        self,
        store: DurableMaintenanceStore,
        signed: SignedDurableMaintenanceEpoch,
    ) -> None:
        if not isinstance(
            store,
            DurableMaintenanceStore,
        ):
            raise TypeError(
                "store must be DurableMaintenanceStore"
            )
        if not isinstance(
            signed,
            SignedDurableMaintenanceEpoch,
        ):
            raise TypeError(
                "signed must be SignedDurableMaintenanceEpoch"
            )
        self.store = store
        self.signed = signed

    def require(
        self,
        *,
        operation: DurableMaintenanceOperation,
        resources: Iterable[str],
        live_resources: Iterable[
            DurableMaintenanceResource
        ] = (),
    ) -> DurableMaintenanceStatus:
        return self.store.require_active(
            self.signed,
            operation=operation,
            required_resources=resources,
            live_resources=live_resources,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "epoch_id": self.signed.epoch_id,
            "operation": (
                self.signed.epoch.operation.value
            ),
            "owner_id": (
                self.signed.epoch.owner_id
            ),
            "resources": list(
                self.signed.epoch.resource_ids
            ),
        }
