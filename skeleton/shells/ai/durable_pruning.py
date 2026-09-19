"""Fenced, resumable hot-tier pruning for archived durable evidence chains.

The executor is intentionally conservative:

1. a current destructive pruning authorization is required;
2. the exact immutable nodes and secondary indexes are snapshotted;
3. a signed monotonic hot floor is committed;
4. only then may hot-tier records be deleted;
5. deletion progress is persisted after every item;
6. resume after a crash is idempotent;
7. any immutable-record substitution moves the operation to manual review.

Journal and receipt chains are supported explicitly because their secondary
indexes differ.  Cross-chain coordination is implemented separately.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import hashlib
import json
import math
import time
from typing import Callable

from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
    DistributedJournalCorruption,
)
from skeleton.shells.ai.durable_archive_store import (
    DurableArchiveRepository,
    DurableArchiveStoreError,
    StoredDurableArchive,
)
from skeleton.shells.ai.distributed_state import (
    DistributedStateConflict,
    FencedLease,
    LeaseConflict,
)
from skeleton.shells.ai.durable_maintenance import (
    DurableMaintenanceOperation,
    DurableMaintenanceResource,
    DurableMaintenanceStale,
    DurableMaintenanceStore,
    SignedDurableMaintenanceEpoch,
)
from skeleton.shells.ai.durable_hot_floor import (
    DurableHotFloorError,
    DurableHotFloorStore,
    SignedDurableHotFloor,
)
from skeleton.shells.ai.durable_pruning_authorization import (
    DurablePruningAuthorizationError,
    DurablePruningAuthorizationStore,
    SignedDurablePruningAuthorization,
)
from skeleton.shells.ai.durable_retention import DurableRetentionPlan
from skeleton.shells.ai.store_protocol import (
    DistributedAIBackend,
)
from skeleton.shells.distributed_receipts import (
    DistributedReceiptChain,
    DistributedReceiptCorruption,
)


def _digest(
    name: str,
    value: str,
    *,
    optional: bool = False,
) -> str:
    if optional and not value:
        return ""
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(
            f"{name} must be 64-character digest"
        )
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


class DurablePruningPhase(str, Enum):
    PREPARED = "prepared"
    FLOOR_COMMITTED = "floor_committed"
    DELETING = "deleting"
    COMPLETE = "complete"
    MANUAL_REVIEW = "manual_review"


class DurablePruningItemKind(str, Enum):
    JOURNAL_EVENT = "journal_event"
    RECEIPT_NODE = "receipt_node"


@dataclass(frozen=True)
class DurablePruningItem:
    sequence: int
    kind: DurablePruningItemKind
    node_hash: str
    node_key: str
    node_revision: int
    sequence_key: str
    sequence_revision: int | None
    receipt_id: str = ""
    receipt_index_key: str = ""
    receipt_index_revision: int | None = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence <= 0
        ):
            raise ValueError(
                "pruning item sequence must be positive"
            )
        object.__setattr__(
            self,
            "kind",
            DurablePruningItemKind(
                self.kind
            ),
        )
        object.__setattr__(
            self,
            "node_hash",
            _digest("node_hash", self.node_hash),
        )
        for name in (
            "node_key",
            "sequence_key",
        ):
            _identity(
                name,
                getattr(self, name),
                maximum=512,
            )
        if (
            isinstance(self.node_revision, bool)
            or not isinstance(self.node_revision, int)
            or self.node_revision <= 0
        ):
            raise ValueError(
                "node_revision must be positive"
            )
        for name in (
            "sequence_revision",
            "receipt_index_revision",
        ):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise ValueError(
                    f"{name} must be positive when present"
                )
        if (
            self.kind
            is DurablePruningItemKind.RECEIPT_NODE
        ):
            _identity(
                "receipt_id",
                self.receipt_id,
                maximum=128,
            )
            _identity(
                "receipt_index_key",
                self.receipt_index_key,
                maximum=512,
            )
        elif (
            self.receipt_id
            or self.receipt_index_key
            or self.receipt_index_revision
            is not None
        ):
            raise ValueError(
                "journal pruning item may not carry receipt index data"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "kind": self.kind.value,
            "node_hash": self.node_hash,
            "node_key": self.node_key,
            "node_revision": self.node_revision,
            "sequence_key": self.sequence_key,
            "sequence_revision": self.sequence_revision,
            "receipt_id": self.receipt_id,
            "receipt_index_key": self.receipt_index_key,
            "receipt_index_revision": (
                self.receipt_index_revision
            ),
        }


@dataclass(frozen=True)
class DurablePruningManifest:
    schema_version: int
    operation_id: str
    chain_id: str
    chain_kind: DurablePruningItemKind
    authorization_id: str
    current_sequence: int
    current_root: str
    previous_floor_sequence: int
    previous_floor_root: str
    cutoff_sequence: int
    cutoff_root: str
    archive_id: str
    archive_manifest_digest: str
    items: tuple[DurablePruningItem, ...]
    created_at: float

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(
                "unsupported pruning manifest schema"
            )
        for name in (
            "operation_id",
            "authorization_id",
            "current_root",
            "previous_floor_root",
            "cutoff_root",
            "archive_manifest_digest",
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
        object.__setattr__(
            self,
            "chain_kind",
            DurablePruningItemKind(
                self.chain_kind
            ),
        )
        _identity(
            "archive_id",
            self.archive_id,
            maximum=256,
        )
        for name in (
            "current_sequence",
            "previous_floor_sequence",
            "cutoff_sequence",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ValueError(
                    f"{name} must be non-negative"
                )
        if self.cutoff_sequence <= 0:
            raise ValueError(
                "cutoff_sequence must be positive"
            )
        if (
            self.previous_floor_sequence
            >= self.cutoff_sequence
        ):
            raise ValueError(
                "pruning cutoff must advance hot floor"
            )
        if self.cutoff_sequence > self.current_sequence:
            raise ValueError(
                "pruning cutoff exceeds current head"
            )
        items = tuple(self.items)
        expected = tuple(
            range(
                self.previous_floor_sequence + 1,
                self.cutoff_sequence + 1,
            )
        )
        actual = tuple(
            item.sequence
            for item in items
        )
        if actual != expected:
            raise ValueError(
                "pruning manifest items must be contiguous ascending prefix"
            )
        if any(
            item.kind is not self.chain_kind
            for item in items
        ):
            raise ValueError(
                "pruning manifest mixes chain item kinds"
            )
        object.__setattr__(
            self,
            "items",
            items,
        )
        if (
            isinstance(self.created_at, bool)
            or not isinstance(self.created_at, (int, float))
            or not math.isfinite(float(self.created_at))
            or float(self.created_at) < 0.0
        ):
            raise ValueError(
                "created_at must be finite and non-negative"
            )
        object.__setattr__(
            self,
            "created_at",
            float(self.created_at),
        )

    @property
    def delete_count(self) -> int:
        return len(self.items)

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
            "schema_version": self.schema_version,
            "operation_id": self.operation_id,
            "chain_id": self.chain_id,
            "chain_kind": self.chain_kind.value,
            "authorization_id": self.authorization_id,
            "current_sequence": self.current_sequence,
            "current_root": self.current_root,
            "previous_floor_sequence": (
                self.previous_floor_sequence
            ),
            "previous_floor_root": (
                self.previous_floor_root
            ),
            "cutoff_sequence": self.cutoff_sequence,
            "cutoff_root": self.cutoff_root,
            "archive_id": self.archive_id,
            "archive_manifest_digest": (
                self.archive_manifest_digest
            ),
            "items": [
                item.to_dict()
                for item in self.items
            ],
            "created_at": self.created_at,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class DurablePruningOperation:
    schema_version: int
    operation_id: str
    chain_id: str
    authorization_id: str
    manifest_digest: str
    phase: DurablePruningPhase
    floor_id: str
    next_delete_index: int
    deleted_items: int
    started_at: float
    updated_at: float
    fencing_token: int
    last_error: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(
                "unsupported pruning operation schema"
            )
        for name in (
            "operation_id",
            "authorization_id",
            "manifest_digest",
        ):
            object.__setattr__(
                self,
                name,
                _digest(name, getattr(self, name)),
            )
        if self.floor_id:
            object.__setattr__(
                self,
                "floor_id",
                _digest(
                    "floor_id",
                    self.floor_id,
                ),
            )
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        object.__setattr__(
            self,
            "phase",
            DurablePruningPhase(self.phase),
        )
        if (
            isinstance(self.next_delete_index, bool)
            or not isinstance(self.next_delete_index, int)
            or self.next_delete_index < -1
        ):
            raise ValueError(
                "next_delete_index must be >= -1"
            )
        for name in (
            "deleted_items",
            "fencing_token",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ValueError(
                    f"{name} must be non-negative"
                )
        if self.fencing_token <= 0:
            raise ValueError(
                "fencing_token must be positive"
            )
        for name in (
            "started_at",
            "updated_at",
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
        if self.updated_at < self.started_at:
            raise ValueError(
                "operation updated_at precedes start"
            )
        if len(self.last_error) > 2048:
            raise ValueError(
                "pruning operation error text too long"
            )

    @property
    def complete(self) -> bool:
        return (
            self.phase
            is DurablePruningPhase.COMPLETE
        )

    @property
    def requires_manual_review(self) -> bool:
        return (
            self.phase
            is DurablePruningPhase.MANUAL_REVIEW
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "operation_id": self.operation_id,
            "chain_id": self.chain_id,
            "authorization_id": self.authorization_id,
            "manifest_digest": self.manifest_digest,
            "phase": self.phase.value,
            "floor_id": self.floor_id,
            "next_delete_index": self.next_delete_index,
            "deleted_items": self.deleted_items,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "fencing_token": self.fencing_token,
            "last_error": self.last_error,
            "complete": self.complete,
            "requires_manual_review": (
                self.requires_manual_review
            ),
        }


@dataclass(frozen=True)
class DurablePruningResult:
    operation: DurablePruningOperation
    manifest: DurablePruningManifest
    floor: SignedDurableHotFloor
    live_verified: bool

    def __post_init__(self) -> None:
        if not isinstance(
            self.operation,
            DurablePruningOperation,
        ):
            raise TypeError(
                "operation must be DurablePruningOperation"
            )
        if not isinstance(
            self.manifest,
            DurablePruningManifest,
        ):
            raise TypeError(
                "manifest must be DurablePruningManifest"
            )
        if not isinstance(
            self.floor,
            SignedDurableHotFloor,
        ):
            raise TypeError(
                "floor must be SignedDurableHotFloor"
            )
        if not isinstance(
            self.live_verified,
            bool,
        ):
            raise ValueError(
                "live_verified must be bool"
            )

    @property
    def ok(self) -> bool:
        return (
            self.operation.complete
            and self.live_verified
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "operation": self.operation.to_dict(),
            "manifest": self.manifest.to_dict(),
            "floor": self.floor.to_dict(),
            "live_verified": self.live_verified,
        }


@dataclass(frozen=True)
class DurablePruningArchiveRecovery:
    chain_id: str
    archive_id: str
    archive_manifest_digest: str
    cutoff_sequence: int
    cutoff_root: str
    archive_revision: int
    archived_nodes: int
    recoverable: bool
    reason: str = ""

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
        object.__setattr__(
            self,
            "archive_manifest_digest",
            _digest(
                "archive_manifest_digest",
                self.archive_manifest_digest,
            ),
        )
        object.__setattr__(
            self,
            "cutoff_root",
            _digest(
                "cutoff_root",
                self.cutoff_root,
            ),
        )
        for name in (
            "cutoff_sequence",
            "archive_revision",
            "archived_nodes",
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
        if self.cutoff_sequence <= 0:
            raise ValueError(
                "cutoff_sequence must be positive"
            )
        if not isinstance(
            self.recoverable,
            bool,
        ):
            raise ValueError(
                "recoverable must be bool"
            )
        if self.recoverable:
            if self.archive_revision <= 0:
                raise ValueError(
                    "recoverable archive requires positive revision"
                )
            if (
                self.archived_nodes
                < self.cutoff_sequence
            ):
                raise ValueError(
                    "recoverable archive must cover cutoff sequence"
                )
            if self.reason:
                raise ValueError(
                    "recoverable archive may not carry failure reason"
                )
        elif len(self.reason) > 2048:
            raise ValueError(
                "archive recovery reason too long"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "chain_id": self.chain_id,
            "archive_id": self.archive_id,
            "archive_manifest_digest": (
                self.archive_manifest_digest
            ),
            "cutoff_sequence": self.cutoff_sequence,
            "cutoff_root": self.cutoff_root,
            "archive_revision": self.archive_revision,
            "archived_nodes": self.archived_nodes,
            "recoverable": self.recoverable,
            "reason": self.reason,
        }


class DurablePruningError(RuntimeError):
    pass


class DurablePruningManualReview(
    DurablePruningError
):
    pass


class DurablePruningExecutor:
    """Execute one authorized hot-prefix pruning operation."""

    def __init__(
        self,
        backend: DistributedAIBackend,
        authorizations: DurablePruningAuthorizationStore,
        hot_floors: DurableHotFloorStore,
        *,
        maintenance: DurableMaintenanceStore | None = None,
        namespace: str = "shell-ai-durable-pruning-operations",
        lease_ttl_seconds: float = 60.0,
        max_items: int = 100_000,
        max_cas_retries: int = 32,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(
            backend,
            DistributedAIBackend,
        ):
            raise TypeError(
                "backend must satisfy DistributedAIBackend"
            )
        if not isinstance(
            authorizations,
            DurablePruningAuthorizationStore,
        ):
            raise TypeError(
                "authorizations must be DurablePruningAuthorizationStore"
            )
        if not isinstance(
            hot_floors,
            DurableHotFloorStore,
        ):
            raise TypeError(
                "hot_floors must be DurableHotFloorStore"
            )
        if not namespace or len(namespace) > 128:
            raise ValueError(
                "invalid pruning operation namespace"
            )
        if (
            isinstance(lease_ttl_seconds, bool)
            or not isinstance(
                lease_ttl_seconds,
                (int, float),
            )
            or not math.isfinite(
                float(lease_ttl_seconds)
            )
            or float(lease_ttl_seconds) <= 0.0
        ):
            raise ValueError(
                "lease_ttl_seconds must be finite and positive"
            )
        if (
            isinstance(max_items, bool)
            or not isinstance(max_items, int)
            or max_items <= 0
        ):
            raise ValueError(
                "max_items must be positive integer"
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
            raise TypeError("clock must be callable")
        if (
            maintenance is not None
            and not isinstance(
                maintenance,
                DurableMaintenanceStore,
            )
        ):
            raise TypeError(
                "maintenance must be DurableMaintenanceStore"
            )
        self.backend = backend
        self.authorizations = authorizations
        self.hot_floors = hot_floors
        archives = getattr(
            getattr(
                authorizations,
                "certificates",
                None,
            ),
            "planner",
            None,
        )
        archives = getattr(
            archives,
            "archives",
            None,
        )
        if not isinstance(
            archives,
            DurableArchiveRepository,
        ):
            raise TypeError(
                "pruning authorization stack must expose DurableArchiveRepository"
            )
        self.archives = archives
        self.maintenance = maintenance
        self.namespace = namespace
        self.lease_ttl_seconds = float(
            lease_ttl_seconds
        )
        self.max_items = max_items
        self.max_cas_retries = (
            max_cas_retries
        )
        self._clock = clock

    def maintenance_resource(
        self,
        chain_id: str,
        chain: object,
    ) -> DurableMaintenanceResource:
        return DurableMaintenanceResource.from_chain(
            chain_id,
            chain,
            resource_kind="evidence-chain",
        )

    def _require_maintenance(
        self,
        chain_id: str,
        chain: object,
        maintenance_epoch: (
            SignedDurableMaintenanceEpoch | None
        ),
    ):
        if self.maintenance is None:
            return None
        if maintenance_epoch is None:
            raise DurablePruningError(
                "durable maintenance epoch is required for pruning"
            )
        if not isinstance(
            maintenance_epoch,
            SignedDurableMaintenanceEpoch,
        ):
            raise TypeError(
                "maintenance_epoch must be SignedDurableMaintenanceEpoch"
            )
        if maintenance_epoch.epoch.operation not in {
            DurableMaintenanceOperation.PRUNING,
            DurableMaintenanceOperation.COMPACTION,
        }:
            raise DurablePruningError(
                "maintenance epoch does not authorize pruning"
            )
        resource = self.maintenance_resource(
            chain_id,
            chain,
        )
        try:
            return self.maintenance.require_active(
                maintenance_epoch,
                required_resources=(chain_id,),
                live_resources=(resource,),
            )
        except DurableMaintenanceStale as exc:
            raise DurablePruningManualReview(
                "durable maintenance authority is stale: "
                + str(exc)
            ) from exc

    @staticmethod
    def derive_operation_id(
        authorization_id: str,
        *,
        previous_floor_sequence: int,
        previous_floor_root: str,
    ) -> str:
        if (
            isinstance(previous_floor_sequence, bool)
            or not isinstance(previous_floor_sequence, int)
            or previous_floor_sequence < 0
        ):
            raise ValueError(
                "previous_floor_sequence must be non-negative"
            )
        _digest(
            "previous_floor_root",
            previous_floor_root,
        )
        payload = {
            "authorization_id": _digest(
                "authorization_id",
                authorization_id,
            ),
            "operation": (
                "durable-hot-tier-pruning"
            ),
        }
        raw = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _manifest_key(
        operation_id: str,
    ) -> str:
        return (
            "manifest:"
            + _digest(
                "operation_id",
                operation_id,
            )
        )

    @staticmethod
    def _operation_key(
        operation_id: str,
    ) -> str:
        return (
            "operation:"
            + _digest(
                "operation_id",
                operation_id,
            )
        )

    @staticmethod
    def _lease_key(
        chain_id: str,
    ) -> str:
        chain_id = _identity(
            "chain_id",
            chain_id,
            maximum=128,
        )
        return (
            "lease:"
            + hashlib.sha256(
                chain_id.encode()
            ).hexdigest()
        )

    @staticmethod
    def _chain_kind(
        chain: object,
    ) -> DurablePruningItemKind:
        if isinstance(
            chain,
            DistributedAIDecisionJournal,
        ):
            return (
                DurablePruningItemKind
                .JOURNAL_EVENT
            )
        if isinstance(
            chain,
            DistributedReceiptChain,
        ):
            return (
                DurablePruningItemKind
                .RECEIPT_NODE
            )
        raise TypeError(
            "pruning supports distributed journal or receipt chain"
        )

    @staticmethod
    def _require_floor_configuration(
        chain: object,
        chain_id: str,
        hot_floors: DurableHotFloorStore,
    ) -> None:
        if getattr(
            chain,
            "hot_floor_store",
            None,
        ) is not hot_floors:
            raise DurablePruningError(
                "chain is not configured with executor hot floor store"
            )
        if getattr(
            chain,
            "hot_floor_chain_id",
            "",
        ) != chain_id:
            raise DurablePruningError(
                "chain hot floor identity differs from pruning chain_id"
            )

    def _now(self) -> float:
        now = self._clock()
        if (
            isinstance(now, bool)
            or not isinstance(now, (int, float))
            or not math.isfinite(float(now))
            or float(now) < 0.0
        ):
            raise DurablePruningError(
                "pruning clock returned invalid time"
            )
        return float(now)

    def _item(
        self,
        chain: object,
        node: object,
        kind: DurablePruningItemKind,
    ) -> DurablePruningItem:
        sequence = int(node.sequence)
        node_hash = str(
            node.event_hash
            if kind
            is DurablePruningItemKind.JOURNAL_EVENT
            else node.receipt_hash
        )
        node_key = (
            chain._event_key(node_hash)
            if kind
            is DurablePruningItemKind.JOURNAL_EVENT
            else chain._node_key(node_hash)
        )
        node_record = self.backend.get(
            chain.namespace,
            node_key,
        )
        if node_record is None:
            raise DurablePruningError(
                "pruning candidate node disappeared before manifest creation"
            )
        sequence_key = chain._sequence_key(
            sequence
        )
        sequence_record = self.backend.get(
            chain.namespace,
            sequence_key,
        )

        if (
            kind
            is DurablePruningItemKind.JOURNAL_EVENT
        ):
            return DurablePruningItem(
                sequence,
                kind,
                node_hash,
                node_key,
                node_record.revision,
                sequence_key,
                (
                    None
                    if sequence_record is None
                    else sequence_record.revision
                ),
            )

        receipt_id = node.receipt.receipt_id
        receipt_index_key = chain._index_key(
            receipt_id
        )
        receipt_index_record = (
            self.backend.get(
                chain.namespace,
                receipt_index_key,
            )
        )
        return DurablePruningItem(
            sequence,
            kind,
            node_hash,
            node_key,
            node_record.revision,
            sequence_key,
            (
                None
                if sequence_record is None
                else sequence_record.revision
            ),
            receipt_id,
            receipt_index_key,
            (
                None
                if receipt_index_record is None
                else receipt_index_record.revision
            ),
        )

    def build_manifest(
        self,
        authorization: SignedDurablePruningAuthorization,
        retention: DurableRetentionPlan,
        chain: object,
    ) -> DurablePruningManifest:
        self._require_floor_configuration(
            chain,
            authorization.authorization.chain_id,
            self.hot_floors,
        )
        self.authorizations.require_current(
            authorization,
            retention,
            chain,
        )
        auth = authorization.authorization
        floor = chain.hot_floor()
        if (
            floor.sequence
            != auth.previous_floor_sequence
            or floor.root_hash
            != auth.previous_floor_root
        ):
            raise DurablePruningError(
                "authorization previous floor differs from live chain"
            )
        if (
            auth.cutoff_sequence
            <= floor.sequence
        ):
            raise DurablePruningError(
                "authorization cutoff does not advance current hot floor"
            )
        delete_count = (
            auth.cutoff_sequence
            - floor.sequence
        )
        if delete_count != auth.delete_count:
            raise DurablePruningError(
                "authorization delete count differs from live floor interval"
            )
        if (
            delete_count > self.max_items
            or delete_count
            > auth.max_delete_items
        ):
            raise DurablePruningError(
                "pruning manifest exceeds deletion bound"
            )
        start = floor.sequence + 1
        nodes = chain.snapshot_range(
            start,
            auth.cutoff_sequence,
            max_items=self.max_items,
        )
        if len(nodes) != delete_count:
            raise DurablePruningError(
                "pruning snapshot length differs from cutoff interval"
            )
        if not nodes:
            raise DurablePruningError(
                "pruning manifest cannot be empty"
            )
        terminal_hash = str(
            nodes[-1].event_hash
            if isinstance(
                chain,
                DistributedAIDecisionJournal,
            )
            else nodes[-1].receipt_hash
        )
        if terminal_hash != auth.cutoff_root:
            raise DurablePruningError(
                "pruning snapshot terminal root differs from authorization"
            )
        head = chain.head()
        if (
            int(head.sequence)
            != auth.current_sequence
            or str(head.root_hash)
            != auth.current_root
        ):
            raise DurablePruningError(
                "live head changed before pruning manifest creation"
            )
        kind = self._chain_kind(chain)
        operation_id = self.derive_operation_id(
            auth.authorization_id,
            previous_floor_sequence=(
                floor.sequence
            ),
            previous_floor_root=(
                floor.root_hash
            ),
        )
        items = tuple(
            self._item(
                chain,
                node,
                kind,
            )
            for node in nodes
        )
        return DurablePruningManifest(
            1,
            operation_id,
            auth.chain_id,
            kind,
            auth.authorization_id,
            auth.current_sequence,
            auth.current_root,
            auth.previous_floor_sequence,
            auth.previous_floor_root,
            auth.cutoff_sequence,
            auth.cutoff_root,
            auth.archive_id,
            auth.archive_manifest_digest,
            items,
            self._now(),
        )

    @staticmethod
    def _manifest_from_dict(
        raw: dict[str, object],
    ) -> DurablePruningManifest:
        items_raw = raw.get("items")
        if not isinstance(items_raw, list):
            raise DurablePruningError(
                "pruning manifest item list invalid"
            )
        items = tuple(
            DurablePruningItem(
                int(item["sequence"]),
                DurablePruningItemKind(
                    str(item["kind"])
                ),
                str(item["node_hash"]),
                str(item["node_key"]),
                int(item["node_revision"]),
                str(item["sequence_key"]),
                (
                    None
                    if item.get(
                        "sequence_revision"
                    ) is None
                    else int(
                        item[
                            "sequence_revision"
                        ]
                    )
                ),
                str(
                    item.get(
                        "receipt_id",
                        "",
                    )
                ),
                str(
                    item.get(
                        "receipt_index_key",
                        "",
                    )
                ),
                (
                    None
                    if item.get(
                        "receipt_index_revision"
                    ) is None
                    else int(
                        item[
                            "receipt_index_revision"
                        ]
                    )
                ),
            )
            for item in items_raw
            if isinstance(item, dict)
        )
        if len(items) != len(items_raw):
            raise DurablePruningError(
                "pruning manifest item shape invalid"
            )
        return DurablePruningManifest(
            int(raw["schema_version"]),
            str(raw["operation_id"]),
            str(raw["chain_id"]),
            DurablePruningItemKind(
                str(raw["chain_kind"])
            ),
            str(raw["authorization_id"]),
            int(raw["current_sequence"]),
            str(raw["current_root"]),
            int(raw["previous_floor_sequence"]),
            str(raw["previous_floor_root"]),
            int(raw["cutoff_sequence"]),
            str(raw["cutoff_root"]),
            str(raw["archive_id"]),
            str(raw["archive_manifest_digest"]),
            items,
            float(raw["created_at"]),
        )

    @staticmethod
    def _operation_from_dict(
        raw: dict[str, object],
    ) -> DurablePruningOperation:
        return DurablePruningOperation(
            int(raw["schema_version"]),
            str(raw["operation_id"]),
            str(raw["chain_id"]),
            str(raw["authorization_id"]),
            str(raw["manifest_digest"]),
            DurablePruningPhase(
                str(raw["phase"])
            ),
            str(raw.get("floor_id", "")),
            int(raw["next_delete_index"]),
            int(raw["deleted_items"]),
            float(raw["started_at"]),
            float(raw["updated_at"]),
            int(raw["fencing_token"]),
            str(raw.get("last_error", "")),
        )

    def _store_manifest(
        self,
        manifest: DurablePruningManifest,
    ) -> None:
        key = self._manifest_key(
            manifest.operation_id
        )
        payload = manifest.to_dict()
        try:
            self.backend.put_if_absent(
                self.namespace,
                key,
                payload,
            )
        except DistributedStateConflict:
            current = self.backend.get(
                self.namespace,
                key,
            )
            if (
                current is None
                or not isinstance(
                    current.value,
                    dict,
                )
            ):
                raise DurablePruningError(
                    "pruning manifest conflict could not be resolved"
                )
            existing = self._manifest_from_dict(
                dict(current.value)
            )
            if existing.digest != manifest.digest:
                raise DurablePruningManualReview(
                    "operation id already binds different pruning manifest"
                )

    def manifest(
        self,
        operation_id: str,
    ) -> DurablePruningManifest | None:
        record = self.backend.get(
            self.namespace,
            self._manifest_key(
                operation_id
            ),
        )
        if record is None:
            return None
        if not isinstance(record.value, dict):
            raise DurablePruningError(
                "pruning manifest record must be mapping"
            )
        manifest = self._manifest_from_dict(
            dict(record.value)
        )
        if (
            manifest.operation_id
            != operation_id
        ):
            raise DurablePruningError(
                "pruning manifest operation identity mismatch"
            )
        return manifest

    def operation(
        self,
        operation_id: str,
    ) -> DurablePruningOperation | None:
        record = self.backend.get(
            self.namespace,
            self._operation_key(
                operation_id
            ),
        )
        if record is None:
            return None
        if not isinstance(record.value, dict):
            raise DurablePruningError(
                "pruning operation record must be mapping"
            )
        item = self._operation_from_dict(
            dict(record.value)
        )
        if item.operation_id != operation_id:
            raise DurablePruningError(
                "pruning operation identity mismatch"
            )
        return item

    def _operation_record(
        self,
        operation_id: str,
    ):
        return self.backend.get(
            self.namespace,
            self._operation_key(
                operation_id
            ),
        )

    def _start_operation(
        self,
        manifest: DurablePruningManifest,
        lease: FencedLease,
    ) -> DurablePruningOperation:
        now = self._now()
        candidate = DurablePruningOperation(
            1,
            manifest.operation_id,
            manifest.chain_id,
            manifest.authorization_id,
            manifest.digest,
            DurablePruningPhase.PREPARED,
            "",
            manifest.delete_count - 1,
            0,
            now,
            now,
            lease.fencing_token,
        )
        key = self._operation_key(
            manifest.operation_id
        )
        try:
            self.backend.put_if_absent(
                self.namespace,
                key,
                candidate.to_dict(),
            )
            return candidate
        except DistributedStateConflict:
            current = self.operation(
                manifest.operation_id
            )
            if current is None:
                raise
            if (
                current.manifest_digest
                != manifest.digest
                or current.authorization_id
                != manifest.authorization_id
            ):
                raise DurablePruningManualReview(
                    "existing pruning operation binds different authority"
                )
            return current

    def _update_operation(
        self,
        current: DurablePruningOperation,
        *,
        phase: DurablePruningPhase | None = None,
        floor_id: str | None = None,
        next_delete_index: int | None = None,
        deleted_items: int | None = None,
        fencing_token: int | None = None,
        last_error: str | None = None,
    ) -> DurablePruningOperation:
        key = self._operation_key(
            current.operation_id
        )
        for _ in range(self.max_cas_retries):
            record = self.backend.get(
                self.namespace,
                key,
            )
            if record is None:
                raise DurablePruningError(
                    "pruning operation disappeared"
                )
            if not isinstance(record.value, dict):
                raise DurablePruningError(
                    "pruning operation record must be mapping"
                )
            latest = self._operation_from_dict(
                dict(record.value)
            )
            if (
                latest.operation_id
                != current.operation_id
                or latest.manifest_digest
                != current.manifest_digest
            ):
                raise DurablePruningManualReview(
                    "pruning operation identity changed"
                )
            updated = replace(
                latest,
                phase=(
                    latest.phase
                    if phase is None
                    else phase
                ),
                floor_id=(
                    latest.floor_id
                    if floor_id is None
                    else floor_id
                ),
                next_delete_index=(
                    latest.next_delete_index
                    if next_delete_index is None
                    else next_delete_index
                ),
                deleted_items=(
                    latest.deleted_items
                    if deleted_items is None
                    else deleted_items
                ),
                fencing_token=(
                    latest.fencing_token
                    if fencing_token is None
                    else fencing_token
                ),
                updated_at=self._now(),
                last_error=(
                    latest.last_error
                    if last_error is None
                    else last_error[:2048]
                ),
            )
            try:
                self.backend.compare_and_swap(
                    self.namespace,
                    key,
                    expected_revision=record.revision,
                    value=updated.to_dict(),
                )
                return updated
            except DistributedStateConflict:
                continue
        raise DurablePruningError(
            "pruning operation CAS retry budget exhausted"
        )

    def _acquire(
        self,
        chain_id: str,
        operator_id: str,
    ) -> FencedLease:
        return self.backend.acquire_lease(
            self.namespace,
            self._lease_key(chain_id),
            owner=operator_id,
            ttl_seconds=self.lease_ttl_seconds,
        )

    def _renew(
        self,
        lease: FencedLease,
    ) -> FencedLease:
        return self.backend.renew_lease(
            lease,
            ttl_seconds=self.lease_ttl_seconds,
        )

    def inspect_archive_recoverability(
        self,
        manifest: DurablePruningManifest,
    ) -> DurablePruningArchiveRecovery:
        if not isinstance(
            manifest,
            DurablePruningManifest,
        ):
            raise TypeError(
                "manifest must be DurablePruningManifest"
            )
        try:
            stored = self._require_archive_recoverability(
                manifest
            )
        except DurablePruningManualReview as exc:
            return DurablePruningArchiveRecovery(
                manifest.chain_id,
                manifest.archive_id,
                manifest.archive_manifest_digest,
                manifest.cutoff_sequence,
                manifest.cutoff_root,
                0,
                0,
                False,
                str(exc)[:2048],
            )
        return DurablePruningArchiveRecovery(
            manifest.chain_id,
            manifest.archive_id,
            manifest.archive_manifest_digest,
            manifest.cutoff_sequence,
            manifest.cutoff_root,
            stored.revision,
            len(stored.node_hashes),
            True,
            "",
        )

    def _require_archive_recoverability(
        self,
        manifest: DurablePruningManifest,
    ) -> StoredDurableArchive:
        """Prove the exact bound archive can recover every pruning item."""
        if not isinstance(
            manifest,
            DurablePruningManifest,
        ):
            raise TypeError(
                "manifest must be DurablePruningManifest"
            )
        try:
            stored = self.archives.require(
                manifest.archive_id
            )
            archived_manifest = (
                stored.manifest.manifest
            )
            if (
                archived_manifest.chain_id
                != manifest.chain_id
                or archived_manifest.digest
                != manifest.archive_manifest_digest
                or archived_manifest.checkpoint_sequence
                != manifest.cutoff_sequence
                or archived_manifest.checkpoint_root
                != manifest.cutoff_root
            ):
                raise DurableArchiveStoreError(
                    "bound archive metadata differs from pruning manifest"
                )
            if len(stored.node_hashes) < manifest.cutoff_sequence:
                raise DurableArchiveStoreError(
                    "bound archive is shorter than pruning cutoff"
                )
            for item in manifest.items:
                position = item.sequence - 1
                if (
                    position < 0
                    or position >= len(stored.node_hashes)
                    or stored.node_hashes[position]
                    != item.node_hash
                ):
                    raise DurableArchiveStoreError(
                        "pruning item is not bound to exact archive position"
                    )
            if not self.archives.verify_root(
                manifest.chain_id,
                manifest.cutoff_root,
            ):
                raise DurableArchiveStoreError(
                    "bound archive cannot verify pruning cutoff root"
                )
            return stored
        except DurableArchiveStoreError as exc:
            raise DurablePruningManualReview(
                "bound archive is not recoverable: "
                + str(exc)
            ) from exc

    def _require_archived_item(
        self,
        manifest: DurablePruningManifest,
        item: DurablePruningItem,
        stored: StoredDurableArchive,
    ) -> None:
        """Require one exact archived object immediately before hot deletion."""
        if (
            stored.manifest.manifest.archive_id
            != manifest.archive_id
            or stored.manifest.manifest.digest
            != manifest.archive_manifest_digest
        ):
            raise DurablePruningManualReview(
                "archive guard no longer matches pruning manifest"
            )
        position = item.sequence - 1
        if (
            position < 0
            or position >= len(stored.node_hashes)
            or stored.node_hashes[position]
            != item.node_hash
        ):
            raise DurablePruningManualReview(
                "pruning item is outside bound archive"
            )
        try:
            archived = self.archives.get_node(
                manifest.chain_id,
                item.node_hash,
            )
        except DurableArchiveStoreError as exc:
            raise DurablePruningManualReview(
                "archived pruning item is unreadable: "
                + str(exc)
            ) from exc
        archived_hash = str(
            getattr(
                archived,
                "event_hash",
                getattr(
                    archived,
                    "receipt_hash",
                    getattr(
                        archived,
                        "node_hash",
                        "",
                    ),
                ),
            )
        )
        if (
            int(getattr(archived, "sequence", -1))
            != item.sequence
            or archived_hash != item.node_hash
        ):
            raise DurablePruningManualReview(
                "archived pruning item identity differs from manifest"
            )

    def _record_matches(
        self,
        namespace: str,
        key: str,
        *,
        expected_revision: int | None,
        expected_value: object | None = None,
    ) -> bool:
        record = self.backend.get(
            namespace,
            key,
        )
        if record is None:
            return False
        if (
            expected_revision is not None
            and record.revision
            != expected_revision
        ):
            raise DurablePruningManualReview(
                "immutable pruning record revision changed"
            )
        if (
            expected_value is not None
            and record.value != expected_value
        ):
            raise DurablePruningManualReview(
                "immutable pruning record content changed"
            )
        return True

    def _delete_record(
        self,
        lease: FencedLease,
        namespace: str,
        key: str,
        expected_revision: int | None,
    ) -> None:
        self.backend.require_fence(lease)
        record = self.backend.get(
            namespace,
            key,
        )
        if record is None:
            return
        if (
            expected_revision is not None
            and record.revision
            != expected_revision
        ):
            raise DurablePruningManualReview(
                "pruning target revision differs from manifest"
            )
        try:
            self.backend.delete(
                namespace,
                key,
                expected_revision=record.revision,
            )
        except DistributedStateConflict as exc:
            retry = self.backend.get(
                namespace,
                key,
            )
            if retry is None:
                return
            raise DurablePruningManualReview(
                "pruning target changed during deletion"
            ) from exc

    def _delete_item(
        self,
        lease: FencedLease,
        chain: object,
        item: DurablePruningItem,
    ) -> None:
        self._delete_record(
            lease,
            chain.namespace,
            item.node_key,
            item.node_revision,
        )
        if item.sequence_revision is not None:
            self._delete_record(
                lease,
                chain.namespace,
                item.sequence_key,
                item.sequence_revision,
            )
        else:
            record = self.backend.get(
                chain.namespace,
                item.sequence_key,
            )
            if record is not None:
                raise DurablePruningManualReview(
                    "sequence index appeared after pruning manifest creation"
                )

        if (
            item.kind
            is DurablePruningItemKind.RECEIPT_NODE
        ):
            if (
                item.receipt_index_revision
                is not None
            ):
                self._delete_record(
                    lease,
                    chain.namespace,
                    item.receipt_index_key,
                    item.receipt_index_revision,
                )
            else:
                record = self.backend.get(
                    chain.namespace,
                    item.receipt_index_key,
                )
                if record is not None:
                    raise DurablePruningManualReview(
                        "receipt index appeared after pruning manifest creation"
                    )

    def prepare(
        self,
        authorization: SignedDurablePruningAuthorization,
        retention: DurableRetentionPlan,
        chain: object,
    ) -> tuple[
        DurablePruningManifest,
        DurablePruningOperation,
    ]:
        auth = authorization.authorization
        lease = self._acquire(
            auth.chain_id,
            auth.operator_id,
        )
        try:
            manifest = self.build_manifest(
                authorization,
                retention,
                chain,
            )
            self._store_manifest(manifest)
            operation = self._start_operation(
                manifest,
                lease,
            )
            if operation.requires_manual_review:
                raise DurablePruningManualReview(
                    operation.last_error
                    or "pruning operation requires manual review"
                )
            return manifest, operation
        finally:
            self.backend.release_lease(
                lease
            )

    def _ensure_floor(
        self,
        manifest: DurablePruningManifest,
        operation: DurablePruningOperation,
        authorization: SignedDurablePruningAuthorization,
        retention: DurableRetentionPlan,
        chain: object,
        lease: FencedLease,
    ) -> tuple[
        DurablePruningOperation,
        SignedDurableHotFloor,
    ]:
        current_floor = chain.hot_floor()
        if (
            current_floor.sequence
            == manifest.cutoff_sequence
            and current_floor.root_hash
            == manifest.cutoff_root
        ):
            floor = self.hot_floors.require_position(
                manifest.chain_id,
                sequence=manifest.cutoff_sequence,
                root_hash=manifest.cutoff_root,
            )
            if (
                floor.floor.operation_id
                != manifest.operation_id
                or floor.floor.pruning_authorization_id
                != manifest.authorization_id
            ):
                raise DurablePruningManualReview(
                    "existing hot floor was committed by different pruning authority"
                )
            if not operation.floor_id:
                operation = self._update_operation(
                    operation,
                    phase=(
                        DurablePruningPhase
                        .FLOOR_COMMITTED
                    ),
                    floor_id=floor.floor_id,
                    fencing_token=(
                        lease.fencing_token
                    ),
                )
            return operation, floor

        if (
            current_floor.sequence
            != manifest.previous_floor_sequence
            or current_floor.root_hash
            != manifest.previous_floor_root
        ):
            raise DurablePruningManualReview(
                "hot floor changed since pruning manifest creation"
            )

        self.backend.require_fence(lease)
        self.authorizations.require_current(
            authorization,
            retention,
            chain,
        )
        head = chain.head()
        if (
            int(head.sequence)
            != manifest.current_sequence
            or str(head.root_hash)
            != manifest.current_root
        ):
            raise DurablePruningError(
                "live head changed before hot floor commit"
            )
        cutoff_root = chain.root_for_sequence(
            manifest.cutoff_sequence,
            repair_missing=False,
        )
        if cutoff_root != manifest.cutoff_root:
            raise DurablePruningManualReview(
                "live cutoff root differs from pruning manifest"
            )

        floor = self.hot_floors.advance(
            chain_id=manifest.chain_id,
            sequence=manifest.cutoff_sequence,
            root_hash=manifest.cutoff_root,
            archive_id=manifest.archive_id,
            archive_manifest_digest=(
                manifest.archive_manifest_digest
            ),
            compaction_certificate_id=(
                authorization.authorization
                .certificate_id
            ),
            pruning_authorization_id=(
                manifest.authorization_id
            ),
            operation_id=manifest.operation_id,
            fencing_token=(
                lease.fencing_token
            ),
            expected_previous_sequence=(
                manifest.previous_floor_sequence
            ),
            expected_previous_root=(
                manifest.previous_floor_root
            ),
        )
        operation = self._update_operation(
            operation,
            phase=(
                DurablePruningPhase
                .FLOOR_COMMITTED
            ),
            floor_id=floor.floor_id,
            fencing_token=(
                lease.fencing_token
            ),
        )
        return operation, floor

    def execute(
        self,
        authorization: SignedDurablePruningAuthorization,
        retention: DurableRetentionPlan,
        chain: object,
        *,
        maintenance_epoch: (
            SignedDurableMaintenanceEpoch | None
        ) = None,
    ) -> DurablePruningResult:
        auth = authorization.authorization
        self._require_floor_configuration(
            chain,
            auth.chain_id,
            self.hot_floors,
        )
        self._require_maintenance(
            auth.chain_id,
            chain,
            maintenance_epoch,
        )
        operation_id = self.derive_operation_id(
            auth.authorization_id,
            previous_floor_sequence=(
                auth.previous_floor_sequence
            ),
            previous_floor_root=(
                auth.previous_floor_root
            ),
        )
        manifest = self.manifest(
            operation_id
        )
        operation = self.operation(
            operation_id
        )

        lease = self._acquire(
            auth.chain_id,
            auth.operator_id,
        )
        try:
            if manifest is None:
                manifest = self.build_manifest(
                    authorization,
                    retention,
                    chain,
                )
                self._store_manifest(
                    manifest
                )
            if operation is None:
                operation = self._start_operation(
                    manifest,
                    lease,
                )
            elif (
                operation.manifest_digest
                != manifest.digest
                or operation.authorization_id
                != auth.authorization_id
            ):
                raise DurablePruningManualReview(
                    "stored pruning operation differs from manifest authority"
                )
            if operation.requires_manual_review:
                raise DurablePruningManualReview(
                    operation.last_error
                    or "pruning operation requires manual review"
                )

            archive_guard = self._require_archive_recoverability(
                manifest
            )
            self._require_maintenance(
                auth.chain_id,
                chain,
                maintenance_epoch,
            )
            operation, floor = self._ensure_floor(
                manifest,
                operation,
                authorization,
                retention,
                chain,
                lease,
            )
            if operation.complete:
                return DurablePruningResult(
                    operation,
                    manifest,
                    floor,
                    bool(chain.verify()),
                )

            if (
                operation.phase
                is DurablePruningPhase.FLOOR_COMMITTED
            ):
                operation = self._update_operation(
                    operation,
                    phase=DurablePruningPhase.DELETING,
                    next_delete_index=(
                        manifest.delete_count - 1
                    ),
                    fencing_token=(
                        lease.fencing_token
                    ),
                )

            while operation.next_delete_index >= 0:
                lease = self._renew(lease)
                self.backend.require_fence(
                    lease
                )
                self._require_maintenance(
                    auth.chain_id,
                    chain,
                    maintenance_epoch,
                )
                index = (
                    operation.next_delete_index
                )
                if index >= manifest.delete_count:
                    raise DurablePruningManualReview(
                        "pruning progress points outside manifest"
                    )
                item = manifest.items[index]
                try:
                    self._require_archived_item(
                        manifest,
                        item,
                        archive_guard,
                    )
                    self._delete_item(
                        lease,
                        chain,
                        item,
                    )
                except DurablePruningManualReview as exc:
                    operation = self._update_operation(
                        operation,
                        phase=(
                            DurablePruningPhase
                            .MANUAL_REVIEW
                        ),
                        fencing_token=(
                            lease.fencing_token
                        ),
                        last_error=str(exc),
                    )
                    raise

                operation = self._update_operation(
                    operation,
                    phase=DurablePruningPhase.DELETING,
                    next_delete_index=(
                        index - 1
                    ),
                    deleted_items=(
                        operation.deleted_items
                        + 1
                    ),
                    fencing_token=(
                        lease.fencing_token
                    ),
                    last_error="",
                )

            # Re-prove the bound archive after the final destructive
            # mutation. Completion means both the surviving live suffix and
            # the archived prefix are independently recoverable.
            self._require_archive_recoverability(
                manifest
            )
            live_verified = bool(
                chain.verify()
            )
            active_floor = chain.hot_floor()
            if (
                not live_verified
                or not chain._hot_floor_active(
                    active_floor
                )
                or active_floor.sequence
                != manifest.cutoff_sequence
                or active_floor.root_hash
                != manifest.cutoff_root
            ):
                operation = self._update_operation(
                    operation,
                    phase=(
                        DurablePruningPhase
                        .MANUAL_REVIEW
                    ),
                    fencing_token=(
                        lease.fencing_token
                    ),
                    last_error=(
                        "live chain failed verification after hot-prefix pruning"
                    ),
                )
                raise DurablePruningManualReview(
                    operation.last_error
                )

            operation = self._update_operation(
                operation,
                phase=DurablePruningPhase.COMPLETE,
                next_delete_index=-1,
                deleted_items=(
                    manifest.delete_count
                ),
                fencing_token=(
                    lease.fencing_token
                ),
                last_error="",
            )
            return DurablePruningResult(
                operation,
                manifest,
                floor,
                live_verified,
            )
        except DurablePruningManualReview as exc:
            if operation is not None and (
                not operation.complete
                and not operation.requires_manual_review
            ):
                try:
                    operation = self._update_operation(
                        operation,
                        phase=(
                            DurablePruningPhase
                            .MANUAL_REVIEW
                        ),
                        fencing_token=(
                            lease.fencing_token
                        ),
                        last_error=str(exc),
                    )
                except Exception:
                    pass
            raise
        except (
            DurablePruningAuthorizationError,
            DurableHotFloorError,
            DistributedJournalCorruption,
            DistributedReceiptCorruption,
            LeaseConflict,
        ) as exc:
            if operation is not None and (
                not operation.complete
                and not operation.requires_manual_review
            ):
                try:
                    operation = self._update_operation(
                        operation,
                        phase=(
                            DurablePruningPhase
                            .MANUAL_REVIEW
                        ),
                        fencing_token=(
                            lease.fencing_token
                        ),
                        last_error=str(exc),
                    )
                except Exception:
                    pass
            raise DurablePruningManualReview(
                str(exc)
            ) from exc
        finally:
            try:
                self.backend.release_lease(
                    lease
                )
            except LeaseConflict:
                pass

    def resume(
        self,
        operation_id: str,
        authorization: SignedDurablePruningAuthorization,
        retention: DurableRetentionPlan,
        chain: object,
        *,
        maintenance_epoch: (
            SignedDurableMaintenanceEpoch | None
        ) = None,
    ) -> DurablePruningResult:
        operation_id = _digest(
            "operation_id",
            operation_id,
        )
        operation = self.operation(
            operation_id
        )
        manifest = self.manifest(
            operation_id
        )
        if operation is None or manifest is None:
            raise DurablePruningError(
                "pruning operation is missing"
            )
        if (
            operation.authorization_id
            != authorization.authorization_id
            or manifest.authorization_id
            != authorization.authorization_id
        ):
            raise DurablePruningManualReview(
                "resume authorization differs from stored operation"
            )
        return self.execute(
            authorization,
            retention,
            chain,
            maintenance_epoch=maintenance_epoch,
        )
