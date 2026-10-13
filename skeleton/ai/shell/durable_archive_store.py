"""Portable durable archive repository and historical read-through resolver.

Archive manifests alone are not sufficient authority for deleting hot evidence:
the actual historical node payloads must remain reconstructable.  This module
stores canonical representations of supported evidence nodes, indexes every
archived prefix root, verifies the existing signed archive/checkpoint authority
before admission, and exposes historical reads without widening execution
authority.

The repository is intentionally non-destructive.  Pruning is a separate,
fenced operation that may rely on this repository only after verification.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import time
from types import MappingProxyType
from typing import Callable

from skeleton.shells.ai.distributed_state import DistributedStateConflict
from skeleton.shells.ai.durable_archive import (
    DurableArchiveEntry,
    DurableArchiveManifest,
    DurableArchiveManifestBuilder,
    SignedDurableArchiveManifest,
)
from skeleton.shells.ai.durable_checkpoint import (
    CheckpointableEvidenceChain,
    DurableChainCheckpoint,
    DurableChainCheckpointStore,
    SignedDurableChainCheckpoint,
)
from skeleton.shells.ai.journal import (
    AIDecisionEvent,
    AIDecisionJournal,
)
from skeleton.shells.ai.signed_artifact import (
    ArtifactSignatureError,
    ArtifactSigner,
    SignedArtifact,
)
from skeleton.shells.ai.store_protocol import VersionedStateBackend
from skeleton.shells.evidence_chain import (
    ContentAddressedEvidenceChain,
    EvidenceNode,
)
from skeleton.shells.sequence_index import SequenceIndexBackfillBatch
from skeleton.shells.receipts import (
    ChainedReceipt,
    ExecutionReceipt,
    ReceiptChain,
)


GENESIS_HASH = "0" * 64


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
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ValueError(f"invalid {name}")
    return value


def _hash_key(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class DurableArchivedNodeType(str, Enum):
    AI_DECISION_EVENT = "ai_decision_event"
    EXECUTION_RECEIPT = "execution_receipt"
    EVIDENCE_NODE = "evidence_node"


@dataclass(frozen=True)
class DurableArchivedNode:
    chain_id: str
    node_type: DurableArchivedNodeType
    sequence: int
    previous_hash: str
    node_hash: str
    object_digest: str
    payload: dict[str, object]

    def __post_init__(self) -> None:
        _identity("chain_id", self.chain_id, maximum=128)
        object.__setattr__(
            self,
            "node_type",
            DurableArchivedNodeType(self.node_type),
        )
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence <= 0
        ):
            raise ValueError("archive node sequence must be positive integer")
        object.__setattr__(
            self,
            "previous_hash",
            _digest("previous_hash", self.previous_hash),
        )
        object.__setattr__(
            self,
            "node_hash",
            _digest("node_hash", self.node_hash),
        )
        object.__setattr__(
            self,
            "object_digest",
            _digest("object_digest", self.object_digest),
        )
        payload = dict(self.payload)
        if len(payload) > 256:
            raise ValueError("archive node payload field bound exceeded")
        object.__setattr__(
            self,
            "payload",
            MappingProxyType(payload),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "chain_id": self.chain_id,
            "node_type": self.node_type.value,
            "sequence": self.sequence,
            "previous_hash": self.previous_hash,
            "node_hash": self.node_hash,
            "object_digest": self.object_digest,
            "payload": dict(self.payload),
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class DurableArchiveRootReplica:
    archive_id: str
    archive_manifest_digest: str

    def __post_init__(self) -> None:
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

    def to_dict(self) -> dict[str, str]:
        return {
            "archive_id": self.archive_id,
            "archive_manifest_digest": (
                self.archive_manifest_digest
            ),
        }


@dataclass(frozen=True)
class DurableArchiveRootIndex:
    chain_id: str
    root_hash: str
    sequence: int
    archive_id: str
    archive_manifest_digest: str
    replicas: tuple[DurableArchiveRootReplica, ...] = ()

    def __post_init__(self) -> None:
        _identity("chain_id", self.chain_id, maximum=128)
        object.__setattr__(
            self,
            "root_hash",
            _digest("root_hash", self.root_hash),
        )
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 0
        ):
            raise ValueError("archive root sequence must be non-negative")
        _identity("archive_id", self.archive_id, maximum=256)
        object.__setattr__(
            self,
            "archive_manifest_digest",
            _digest(
                "archive_manifest_digest",
                self.archive_manifest_digest,
            ),
        )
        replicas = tuple(self.replicas)
        primary = DurableArchiveRootReplica(
            self.archive_id,
            self.archive_manifest_digest,
        )
        if not replicas:
            replicas = (primary,)
        elif replicas[0] != primary:
            raise ValueError(
                "archive root replica list must begin with primary archive"
            )
        archive_ids = tuple(
            item.archive_id
            for item in replicas
        )
        if len(archive_ids) != len(
            set(archive_ids)
        ):
            raise ValueError(
                "duplicate archive root replica"
            )
        object.__setattr__(
            self,
            "replicas",
            replicas,
        )
        if self.sequence == 0 and self.root_hash != GENESIS_HASH:
            raise ValueError("genesis archive root index must use genesis hash")
        if self.sequence > 0 and self.root_hash == GENESIS_HASH:
            raise ValueError("non-genesis archive root may not use genesis hash")

    def to_dict(self) -> dict[str, object]:
        return {
            "chain_id": self.chain_id,
            "root_hash": self.root_hash,
            "sequence": self.sequence,
            "archive_id": self.archive_id,
            "archive_manifest_digest": self.archive_manifest_digest,
            "replicas": [
                item.to_dict()
                for item in self.replicas
            ],
        }


@dataclass(frozen=True)
class DurableArchiveSequenceIndex:
    chain_id: str
    sequence: int
    root_hash: str

    def __post_init__(self) -> None:
        _identity("chain_id", self.chain_id, maximum=128)
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 0
        ):
            raise ValueError(
                "archive sequence index must be non-negative"
            )
        object.__setattr__(
            self,
            "root_hash",
            _digest("root_hash", self.root_hash),
        )
        if self.sequence == 0 and self.root_hash != GENESIS_HASH:
            raise ValueError(
                "genesis archive sequence index must use genesis hash"
            )
        if self.sequence > 0 and self.root_hash == GENESIS_HASH:
            raise ValueError(
                "non-genesis archive sequence may not use genesis hash"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "chain_id": self.chain_id,
            "sequence": self.sequence,
            "root_hash": self.root_hash,
        }


@dataclass(frozen=True)
class DurableArchiveSequenceIndexHealth:
    head_sequence: int
    inspected: int
    indexed: int
    missing: int
    corrupt: int
    first_missing_sequence: int | None = None
    first_corrupt_sequence: int | None = None

    def __post_init__(self) -> None:
        for name in (
            "head_sequence",
            "inspected",
            "indexed",
            "missing",
            "corrupt",
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
        for name in (
            "first_missing_sequence",
            "first_corrupt_sequence",
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

    @property
    def healthy(self) -> bool:
        return self.missing == 0 and self.corrupt == 0

    def to_dict(self) -> dict[str, object]:
        return {
            "head_sequence": self.head_sequence,
            "inspected": self.inspected,
            "indexed": self.indexed,
            "missing": self.missing,
            "corrupt": self.corrupt,
            "first_missing_sequence": (
                self.first_missing_sequence
            ),
            "first_corrupt_sequence": (
                self.first_corrupt_sequence
            ),
            "healthy": self.healthy,
        }


@dataclass(frozen=True)
class DurableArchiveRootResolution:
    chain_id: str
    root_hash: str
    sequence: int
    archive_id: str
    archive_manifest_digest: str
    replica_index: int

    def __post_init__(self) -> None:
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        object.__setattr__(
            self,
            "root_hash",
            _digest(
                "root_hash",
                self.root_hash,
            ),
        )
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 0
        ):
            raise ValueError(
                "archive root resolution sequence must be non-negative"
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
        if (
            isinstance(self.replica_index, bool)
            or not isinstance(self.replica_index, int)
            or self.replica_index < 0
        ):
            raise ValueError(
                "replica_index must be non-negative integer"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "chain_id": self.chain_id,
            "root_hash": self.root_hash,
            "sequence": self.sequence,
            "archive_id": self.archive_id,
            "archive_manifest_digest": (
                self.archive_manifest_digest
            ),
            "replica_index": self.replica_index,
        }


@dataclass(frozen=True)
class DurableArchiveHead:
    chain_id: str
    sequence: int
    root_hash: str
    archive_id: str
    archive_manifest_digest: str

    def __post_init__(self) -> None:
        _identity("chain_id", self.chain_id, maximum=128)
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 0
        ):
            raise ValueError("archive head sequence must be non-negative")
        object.__setattr__(
            self,
            "root_hash",
            _digest("root_hash", self.root_hash),
        )
        _identity("archive_id", self.archive_id, maximum=256)
        object.__setattr__(
            self,
            "archive_manifest_digest",
            _digest(
                "archive_manifest_digest",
                self.archive_manifest_digest,
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "chain_id": self.chain_id,
            "sequence": self.sequence,
            "root_hash": self.root_hash,
            "archive_id": self.archive_id,
            "archive_manifest_digest": self.archive_manifest_digest,
        }


@dataclass(frozen=True)
class StoredDurableArchive:
    revision: int
    manifest: SignedDurableArchiveManifest
    checkpoint: SignedDurableChainCheckpoint
    node_hashes: tuple[str, ...]
    stored_at: float

    def __post_init__(self) -> None:
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision <= 0
        ):
            raise ValueError("archive revision must be positive")
        object.__setattr__(
            self,
            "node_hashes",
            tuple(
                _digest("node_hash", item)
                for item in self.node_hashes
            ),
        )
        if len(self.node_hashes) != self.manifest.manifest.node_count:
            raise ValueError("archive node hash count differs from manifest")
        if (
            isinstance(self.stored_at, bool)
            or not isinstance(self.stored_at, (int, float))
            or not math.isfinite(float(self.stored_at))
            or float(self.stored_at) < 0.0
        ):
            raise ValueError("archive stored_at must be finite and non-negative")
        object.__setattr__(self, "stored_at", float(self.stored_at))

    def to_dict(self) -> dict[str, object]:
        return {
            "revision": self.revision,
            "manifest": self.manifest.to_dict(),
            "checkpoint": self.checkpoint.to_dict(),
            "node_hashes": list(self.node_hashes),
            "stored_at": self.stored_at,
        }


@dataclass(frozen=True)
class DurableArchiveStoreReport:
    archive_id: str
    chain_id: str
    sequence: int
    root_hash: str
    node_count: int
    manifest_digest: str
    checkpoint_digest: str
    fresh_write: bool
    repaired_indexes: int

    def __post_init__(self) -> None:
        _identity("archive_id", self.archive_id, maximum=256)
        _identity("chain_id", self.chain_id, maximum=128)
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 0
        ):
            raise ValueError("archive store sequence must be non-negative")
        object.__setattr__(
            self,
            "root_hash",
            _digest("root_hash", self.root_hash),
        )
        if (
            isinstance(self.node_count, bool)
            or not isinstance(self.node_count, int)
            or self.node_count < 0
        ):
            raise ValueError("archive node_count must be non-negative")
        object.__setattr__(
            self,
            "manifest_digest",
            _digest("manifest_digest", self.manifest_digest),
        )
        object.__setattr__(
            self,
            "checkpoint_digest",
            _digest("checkpoint_digest", self.checkpoint_digest),
        )
        if not isinstance(self.fresh_write, bool):
            raise ValueError("fresh_write must be bool")
        if (
            isinstance(self.repaired_indexes, bool)
            or not isinstance(self.repaired_indexes, int)
            or self.repaired_indexes < 0
        ):
            raise ValueError("repaired_indexes must be non-negative")

    def to_dict(self) -> dict[str, object]:
        return {
            "archive_id": self.archive_id,
            "chain_id": self.chain_id,
            "sequence": self.sequence,
            "root_hash": self.root_hash,
            "node_count": self.node_count,
            "manifest_digest": self.manifest_digest,
            "checkpoint_digest": self.checkpoint_digest,
            "fresh_write": self.fresh_write,
            "repaired_indexes": self.repaired_indexes,
        }


class DurableArchiveStoreError(RuntimeError):
    pass


class DurableArchiveIndexState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    INVALID = "invalid"


@dataclass(frozen=True)
class DurableArchiveIndexHealth:
    archive_id: str
    chain_id: str
    state: DurableArchiveIndexState
    archive_valid: bool
    expected_root_indexes: int
    root_indexes_present: int
    replica_bindings_present: int
    missing_root_indexes: tuple[str, ...]
    missing_replica_roots: tuple[str, ...]
    corrupt_root_indexes: tuple[str, ...]
    head_repair_required: bool
    head_valid: bool

    def __post_init__(self) -> None:
        _identity(
            "archive_id",
            self.archive_id,
            maximum=160,
        )
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        object.__setattr__(
            self,
            "state",
            DurableArchiveIndexState(
                self.state
            ),
        )
        for name in (
            "archive_valid",
            "head_repair_required",
            "head_valid",
        ):
            if not isinstance(
                getattr(self, name),
                bool,
            ):
                raise ValueError(
                    f"{name} must be bool"
                )
        for name in (
            "expected_root_indexes",
            "root_indexes_present",
            "replica_bindings_present",
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
        if (
            self.root_indexes_present
            > self.expected_root_indexes
        ):
            raise ValueError(
                "root_indexes_present exceeds expected count"
            )
        if (
            self.replica_bindings_present
            > self.expected_root_indexes
        ):
            raise ValueError(
                "replica_bindings_present exceeds expected count"
            )
        for name in (
            "missing_root_indexes",
            "missing_replica_roots",
            "corrupt_root_indexes",
        ):
            values = tuple(
                getattr(self, name)
            )
            for value in values:
                _digest(name, value)
            if len(values) != len(set(values)):
                raise ValueError(
                    f"duplicate {name}"
                )
            object.__setattr__(
                self,
                name,
                values,
            )

    @property
    def missing(self) -> int:
        return (
            len(self.missing_root_indexes)
            + len(self.missing_replica_roots)
            + int(self.head_repair_required)
        )

    @property
    def corrupt(self) -> int:
        return len(
            self.corrupt_root_indexes
        ) + int(not self.head_valid)

    @property
    def healthy(self) -> bool:
        return (
            self.state
            is DurableArchiveIndexState.HEALTHY
        )

    @property
    def repairable(self) -> bool:
        return (
            self.archive_valid
            and self.state
            is DurableArchiveIndexState.DEGRADED
            and self.corrupt == 0
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "archive_id": self.archive_id,
            "chain_id": self.chain_id,
            "state": self.state.value,
            "archive_valid": self.archive_valid,
            "expected_root_indexes": self.expected_root_indexes,
            "root_indexes_present": self.root_indexes_present,
            "replica_bindings_present": self.replica_bindings_present,
            "missing_root_indexes": list(
                self.missing_root_indexes
            ),
            "missing_replica_roots": list(
                self.missing_replica_roots
            ),
            "corrupt_root_indexes": list(
                self.corrupt_root_indexes
            ),
            "head_repair_required": self.head_repair_required,
            "head_valid": self.head_valid,
            "missing": self.missing,
            "corrupt": self.corrupt,
            "healthy": self.healthy,
            "repairable": self.repairable,
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()


class DurableArchiveRepository:
    """CAS-backed repository containing signed archive metadata and node payloads."""

    def __init__(
        self,
        backend: VersionedStateBackend,
        checkpoints: DurableChainCheckpointStore,
        archive_signer: ArtifactSigner,
        *,
        namespace: str = "shell-ai-durable-archive-store",
        max_nodes_per_archive: int = 100_000,
        max_cas_retries: int = 32,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(backend, VersionedStateBackend):
            raise TypeError("backend must satisfy VersionedStateBackend")
        if not isinstance(checkpoints, DurableChainCheckpointStore):
            raise TypeError("checkpoints must be DurableChainCheckpointStore")
        if not isinstance(archive_signer, ArtifactSigner):
            raise TypeError("archive_signer must be ArtifactSigner")
        if not namespace or len(namespace) > 128:
            raise ValueError("invalid durable archive store namespace")
        if (
            isinstance(max_nodes_per_archive, bool)
            or not isinstance(max_nodes_per_archive, int)
            or max_nodes_per_archive <= 0
        ):
            raise ValueError("max_nodes_per_archive must be positive integer")
        if (
            isinstance(max_cas_retries, bool)
            or not isinstance(max_cas_retries, int)
            or not 1 <= max_cas_retries <= 128
        ):
            raise ValueError("max_cas_retries outside supported range")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self.backend = backend
        self.checkpoints = checkpoints
        self.archive_signer = archive_signer
        self.namespace = namespace
        self.max_nodes_per_archive = max_nodes_per_archive
        self.max_cas_retries = max_cas_retries
        self._clock = clock
        self._builder = DurableArchiveManifestBuilder(
            checkpoints,
            archive_signer,
            clock=clock,
            max_entries=max_nodes_per_archive,
        )

    @staticmethod
    def _record_digest(
        *,
        manifest_digest: str,
        checkpoint_digest: str,
        node_hashes: tuple[str, ...],
        stored_at: float,
    ) -> str:
        raw = json.dumps(
            {
                "manifest_digest": _digest(
                    "manifest_digest",
                    manifest_digest,
                ),
                "checkpoint_digest": _digest(
                    "checkpoint_digest",
                    checkpoint_digest,
                ),
                "node_hashes": [
                    _digest("node_hash", item)
                    for item in node_hashes
                ],
                "stored_at": float(stored_at),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _archive_key(archive_id: str) -> str:
        return "archive:" + _hash_key(
            _identity("archive_id", archive_id, maximum=256)
        )

    @staticmethod
    def _node_key(chain_id: str, node_hash: str) -> str:
        return (
            "node:"
            + _hash_key(
                _identity("chain_id", chain_id, maximum=128)
            )
            + ":"
            + _digest("node_hash", node_hash)
        )

    @staticmethod
    def _root_key(chain_id: str, root_hash: str) -> str:
        return (
            "root:"
            + _hash_key(
                _identity("chain_id", chain_id, maximum=128)
            )
            + ":"
            + _digest("root_hash", root_hash)
        )

    @staticmethod
    def _sequence_key(
        chain_id: str,
        sequence: int,
    ) -> str:
        _identity("chain_id", chain_id, maximum=128)
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence < 0
        ):
            raise ValueError(
                "archive sequence must be non-negative integer"
            )
        return (
            "sequence:"
            + _hash_key(chain_id)
            + ":"
            + f"{sequence:020d}"
        )

    @staticmethod
    def _head_key(chain_id: str) -> str:
        return "head:" + _hash_key(
            _identity("chain_id", chain_id, maximum=128)
        )

    @staticmethod
    def _signature(raw: dict[str, object]) -> SignedArtifact:
        return SignedArtifact(
            str(raw["artifact_type"]),
            str(raw["artifact_digest"]),
            str(raw["key_id"]),
            float(raw["issued_at"]),
            dict(raw.get("metadata", {})),
            str(raw["signature"]),
        )

    @classmethod
    def _manifest(
        cls,
        raw: dict[str, object],
    ) -> SignedDurableArchiveManifest:
        manifest_raw = raw.get("manifest")
        signature_raw = raw.get("signature")
        if not isinstance(manifest_raw, dict) or not isinstance(signature_raw, dict):
            raise DurableArchiveStoreError("archive manifest record shape invalid")
        entries_raw = manifest_raw.get("entries", ())
        if not isinstance(entries_raw, (list, tuple)):
            raise DurableArchiveStoreError("archive manifest entries shape invalid")
        entries = tuple(
            DurableArchiveEntry(
                int(item["sequence"]),
                str(item["previous_hash"]),
                str(item["node_hash"]),
                str(item["kind"]),
                str(item["object_digest"]),
            )
            for item in entries_raw
            if isinstance(item, dict)
        )
        if len(entries) != len(entries_raw):
            raise DurableArchiveStoreError("archive manifest entry must be mapping")
        manifest = DurableArchiveManifest(
            int(manifest_raw["schema_version"]),
            str(manifest_raw["archive_id"]),
            str(manifest_raw["chain_id"]),
            str(manifest_raw["checkpoint_digest"]),
            int(manifest_raw["checkpoint_sequence"]),
            str(manifest_raw["checkpoint_root"]),
            int(manifest_raw["node_count"]),
            str(manifest_raw["entries_digest"]),
            entries,
            float(manifest_raw["created_at"]),
        )
        return SignedDurableArchiveManifest(
            manifest,
            cls._signature(dict(signature_raw)),
        )

    @classmethod
    def _checkpoint(
        cls,
        raw: dict[str, object],
    ) -> SignedDurableChainCheckpoint:
        checkpoint_raw = raw.get("checkpoint")
        signature_raw = raw.get("signature")
        if not isinstance(checkpoint_raw, dict) or not isinstance(signature_raw, dict):
            raise DurableArchiveStoreError("archive checkpoint record shape invalid")
        checkpoint = DurableChainCheckpoint(
            int(checkpoint_raw["schema_version"]),
            str(checkpoint_raw["chain_id"]),
            int(checkpoint_raw["sequence"]),
            str(checkpoint_raw["root_hash"]),
            str(checkpoint_raw.get("previous_checkpoint_digest", "")),
            float(checkpoint_raw["observed_at"]),
        )
        return SignedDurableChainCheckpoint(
            checkpoint,
            cls._signature(dict(signature_raw)),
            str(raw["chain_node_hash"]),
        )

    @staticmethod
    def _encode_node(
        chain_id: str,
        node,
    ) -> DurableArchivedNode:
        if isinstance(node, AIDecisionEvent):
            return DurableArchivedNode(
                chain_id,
                DurableArchivedNodeType.AI_DECISION_EVENT,
                node.sequence,
                node.previous_hash,
                node.event_hash,
                node.event_hash,
                node.to_dict(),
            )
        if isinstance(node, ChainedReceipt):
            return DurableArchivedNode(
                chain_id,
                DurableArchivedNodeType.EXECUTION_RECEIPT,
                node.sequence,
                node.previous_hash,
                node.receipt_hash,
                node.receipt.fingerprint,
                node.to_dict(),
            )
        if isinstance(node, EvidenceNode):
            return DurableArchivedNode(
                chain_id,
                DurableArchivedNodeType.EVIDENCE_NODE,
                node.sequence,
                node.previous_hash,
                node.node_hash,
                node.node_hash,
                node.to_dict(),
            )
        raise DurableArchiveStoreError(
            f"unsupported archive node type: {type(node).__name__}"
        )

    @staticmethod
    def _decode_receipt(raw: dict[str, object]) -> ExecutionReceipt:
        return ExecutionReceipt(
            command=str(raw["command"]),
            correlation_id=str(raw["correlation_id"]),
            fingerprint=str(raw["fingerprint"]),
            started_at=str(raw["started_at"]),
            finished_at=str(raw["finished_at"]),
            duration_ms=float(raw["duration_ms"]),
            returncode=(
                None
                if raw.get("returncode") is None
                else int(raw["returncode"])
            ),
            ok=bool(raw["ok"]),
            timed_out=bool(raw["timed_out"]),
            output_limited=bool(raw["output_limited"]),
            stdout_bytes=int(raw["stdout_bytes"]),
            stderr_bytes=int(raw["stderr_bytes"]),
            attempt=int(raw.get("attempt", 1)),
            receipt_id=str(raw["receipt_id"]),
            metadata=dict(raw.get("metadata", {})),
        )

    @classmethod
    def _decode_node(
        cls,
        archived: DurableArchivedNode,
    ):
        raw = dict(archived.payload)
        if archived.node_type is DurableArchivedNodeType.AI_DECISION_EVENT:
            node = AIDecisionEvent(
                int(raw["sequence"]),
                str(raw["previous_hash"]),
                str(raw["event_hash"]),
                str(raw["kind"]),
                float(raw["observed_at"]),
                str(raw["session_id"]),
                str(raw["intent_id"]),
                str(raw.get("proposal_id", "")),
                str(raw.get("summary", "")),
                MappingProxyType(dict(raw.get("data", {}))),
            )
            expected = AIDecisionJournal._hash(
                node.previous_hash,
                node.sequence,
                node.kind,
                node.observed_at,
                node.session_id,
                node.intent_id,
                node.proposal_id,
                node.summary,
                node.data,
            )
            node_hash = node.event_hash
            object_digest = node.event_hash
        elif archived.node_type is DurableArchivedNodeType.EXECUTION_RECEIPT:
            receipt_raw = raw.get("receipt")
            if not isinstance(receipt_raw, dict):
                raise DurableArchiveStoreError("archived receipt payload is invalid")
            receipt = cls._decode_receipt(dict(receipt_raw))
            node = ChainedReceipt(
                int(raw["sequence"]),
                str(raw["previous_hash"]),
                str(raw["receipt_hash"]),
                receipt,
            )
            expected = ReceiptChain._hash(
                node.previous_hash,
                node.sequence,
                node.receipt,
            )
            node_hash = node.receipt_hash
            object_digest = node.receipt.fingerprint
        elif archived.node_type is DurableArchivedNodeType.EVIDENCE_NODE:
            payload_raw = raw.get("payload")
            if not isinstance(payload_raw, dict):
                raise DurableArchiveStoreError("archived evidence payload is invalid")
            node = EvidenceNode(
                int(raw["sequence"]),
                str(raw["previous_hash"]),
                str(raw["node_hash"]),
                str(raw["kind"]),
                dict(payload_raw),
            )
            expected = ContentAddressedEvidenceChain.node_digest(
                node.previous_hash,
                node.sequence,
                node.kind,
                node.payload,
            )
            node_hash = node.node_hash
            object_digest = node.node_hash
        else:
            raise DurableArchiveStoreError("unsupported archived node type")

        if expected != node_hash:
            raise DurableArchiveStoreError("archived node native digest mismatch")
        if archived.sequence != node.sequence:
            raise DurableArchiveStoreError("archived node sequence mismatch")
        if archived.previous_hash != node.previous_hash:
            raise DurableArchiveStoreError("archived node previous hash mismatch")
        if archived.node_hash != node_hash:
            raise DurableArchiveStoreError("archived node hash mismatch")
        if archived.object_digest != object_digest:
            raise DurableArchiveStoreError("archived node object digest mismatch")
        return node

    @classmethod
    def _archived_node(
        cls,
        raw: dict[str, object],
    ) -> DurableArchivedNode:
        payload = raw.get("payload")
        if not isinstance(payload, dict):
            raise DurableArchiveStoreError("archived node payload must be mapping")
        return DurableArchivedNode(
            str(raw["chain_id"]),
            DurableArchivedNodeType(str(raw["node_type"])),
            int(raw["sequence"]),
            str(raw["previous_hash"]),
            str(raw["node_hash"]),
            str(raw["object_digest"]),
            dict(payload),
        )

    @staticmethod
    def _root_index(raw: dict[str, object]) -> DurableArchiveRootIndex:
        replicas_raw = raw.get(
            "replicas",
            (),
        )
        if not isinstance(
            replicas_raw,
            (list, tuple),
        ):
            raise DurableArchiveStoreError(
                "archive root replicas must be a sequence"
            )
        replicas = tuple(
            DurableArchiveRootReplica(
                str(item["archive_id"]),
                str(
                    item[
                        "archive_manifest_digest"
                    ]
                ),
            )
            for item in replicas_raw
            if isinstance(item, dict)
        )
        if len(replicas) != len(
            replicas_raw
        ):
            raise DurableArchiveStoreError(
                "archive root replica must be mapping"
            )
        return DurableArchiveRootIndex(
            str(raw["chain_id"]),
            str(raw["root_hash"]),
            int(raw["sequence"]),
            str(raw["archive_id"]),
            str(raw["archive_manifest_digest"]),
            replicas,
        )

    @staticmethod
    def _sequence_index(
        raw: dict[str, object],
    ) -> DurableArchiveSequenceIndex:
        try:
            return DurableArchiveSequenceIndex(
                str(raw["chain_id"]),
                int(raw["sequence"]),
                str(raw["root_hash"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise DurableArchiveStoreError(
                "archive sequence index is malformed"
            ) from exc

    @staticmethod
    def _head(raw: dict[str, object]) -> DurableArchiveHead:
        return DurableArchiveHead(
            str(raw["chain_id"]),
            int(raw["sequence"]),
            str(raw["root_hash"]),
            str(raw["archive_id"]),
            str(raw["archive_manifest_digest"]),
        )

    def _verify_manifest_signature(
        self,
        item: SignedDurableArchiveManifest,
    ) -> None:
        manifest = item.manifest
        signature = item.signature
        if signature.artifact_type != "durable-archive-manifest":
            raise DurableArchiveStoreError("archive manifest artifact type mismatch")
        if signature.artifact_digest != manifest.digest:
            raise DurableArchiveStoreError("archive manifest signature digest mismatch")
        if signature.metadata.get("archive_id") != manifest.archive_id:
            raise DurableArchiveStoreError("archive manifest signature archive_id mismatch")
        if signature.metadata.get("chain_id") != manifest.chain_id:
            raise DurableArchiveStoreError("archive manifest signature chain_id mismatch")
        if signature.metadata.get("checkpoint_digest") != manifest.checkpoint_digest:
            raise DurableArchiveStoreError(
                "archive manifest signature checkpoint digest mismatch"
            )
        try:
            self.archive_signer.verify(signature)
        except ArtifactSignatureError as exc:
            raise DurableArchiveStoreError(
                "archive manifest signature verification failed"
            ) from exc

    def _verify_checkpoint_authority(
        self,
        checkpoint: SignedDurableChainCheckpoint,
    ) -> None:
        try:
            canonical = self.checkpoints.find_by_digest(
                checkpoint.checkpoint.digest
            )
        except Exception as exc:
            raise DurableArchiveStoreError(
                "archive checkpoint canonical lookup failed"
            ) from exc
        if canonical is None:
            raise DurableArchiveStoreError(
                "archive checkpoint is not present in canonical registry"
            )
        if canonical != checkpoint:
            raise DurableArchiveStoreError(
                "archive checkpoint differs from canonical registry item"
            )
        if (
            canonical.checkpoint.chain_id
            != checkpoint.checkpoint.chain_id
        ):
            raise DurableArchiveStoreError(
                "archive checkpoint canonical chain mismatch"
            )

    def _put_immutable(
        self,
        key: str,
        value: object,
        *,
        conflict_message: str,
    ) -> bool:
        existing = self.backend.get(self.namespace, key)
        if existing is None:
            try:
                self.backend.put_if_absent(
                    self.namespace,
                    key,
                    value,
                )
                return True
            except DistributedStateConflict:
                existing = self.backend.get(self.namespace, key)
                if existing is None:
                    raise
        if existing.value != value:
            raise DurableArchiveStoreError(conflict_message)
        return False

    def _put_node(
        self,
        node: DurableArchivedNode,
    ) -> bool:
        return self._put_immutable(
            self._node_key(node.chain_id, node.node_hash),
            node.to_dict(),
            conflict_message="archive node hash already binds different payload",
        )

    def _put_root_index(
        self,
        item: DurableArchiveRootIndex,
    ) -> bool:
        key = self._root_key(
            item.chain_id,
            item.root_hash,
        )
        candidate_replica = (
            DurableArchiveRootReplica(
                item.archive_id,
                item.archive_manifest_digest,
            )
        )
        for _ in range(
            self.max_cas_retries
        ):
            existing = self.backend.get(
                self.namespace,
                key,
            )
            if existing is None:
                try:
                    self.backend.put_if_absent(
                        self.namespace,
                        key,
                        item.to_dict(),
                    )
                    return True
                except DistributedStateConflict:
                    continue
            if not isinstance(
                existing.value,
                dict,
            ):
                raise DurableArchiveStoreError(
                    "archive root index must be mapping"
                )
            current = self._root_index(
                dict(existing.value)
            )
            if (
                current.chain_id
                != item.chain_id
                or current.root_hash
                != item.root_hash
                or current.sequence
                != item.sequence
            ):
                raise DurableArchiveStoreError(
                    "archive root already binds incompatible historical position"
                )
            for replica in current.replicas:
                if (
                    replica.archive_id
                    == item.archive_id
                ):
                    if (
                        replica.archive_manifest_digest
                        != item.archive_manifest_digest
                    ):
                        raise DurableArchiveStoreError(
                            "archive root replica id binds different manifest"
                        )
                    return False
            updated = DurableArchiveRootIndex(
                current.chain_id,
                current.root_hash,
                current.sequence,
                current.archive_id,
                current.archive_manifest_digest,
                current.replicas
                + (candidate_replica,),
            )
            try:
                self.backend.compare_and_swap(
                    self.namespace,
                    key,
                    expected_revision=(
                        existing.revision
                    ),
                    value=updated.to_dict(),
                )
                return True
            except DistributedStateConflict:
                continue
        raise DurableArchiveStoreError(
            "archive root replica CAS retry budget exhausted"
        )

    def _put_sequence_index(
        self,
        item: DurableArchiveSequenceIndex,
    ) -> bool:
        return self._put_immutable(
            self._sequence_key(
                item.chain_id,
                item.sequence,
            ),
            item.to_dict(),
            conflict_message=(
                "archive sequence already binds different historical root"
            ),
        )

    def _update_head(
        self,
        candidate: DurableArchiveHead,
    ) -> None:
        key = self._head_key(candidate.chain_id)
        for _ in range(self.max_cas_retries):
            record = self.backend.get(self.namespace, key)
            if record is None:
                try:
                    self.backend.put_if_absent(
                        self.namespace,
                        key,
                        candidate.to_dict(),
                    )
                    return
                except DistributedStateConflict:
                    continue
            if not isinstance(record.value, dict):
                raise DurableArchiveStoreError("archive head record must be mapping")
            current = self._head(dict(record.value))
            if current.chain_id != candidate.chain_id:
                raise DurableArchiveStoreError("archive head chain_id mismatch")
            if current.sequence > candidate.sequence:
                return
            if current.sequence == candidate.sequence:
                if current != candidate:
                    raise DurableArchiveStoreError(
                        "same archive head sequence binds different root"
                    )
                return
            try:
                self.backend.compare_and_swap(
                    self.namespace,
                    key,
                    expected_revision=record.revision,
                    value=candidate.to_dict(),
                )
                return
            except DistributedStateConflict:
                continue
        raise DurableArchiveStoreError("archive head CAS retry budget exhausted")

    def put(
        self,
        item: SignedDurableArchiveManifest,
        checkpoint: SignedDurableChainCheckpoint,
        chain: CheckpointableEvidenceChain,
    ) -> DurableArchiveStoreReport:
        if not isinstance(item, SignedDurableArchiveManifest):
            raise TypeError("item must be SignedDurableArchiveManifest")
        if not isinstance(checkpoint, SignedDurableChainCheckpoint):
            raise TypeError("checkpoint must be SignedDurableChainCheckpoint")
        if not isinstance(chain, CheckpointableEvidenceChain):
            raise TypeError("chain must satisfy CheckpointableEvidenceChain")

        self._verify_manifest_signature(item)
        self._verify_checkpoint_authority(checkpoint)
        try:
            verification = self._builder.require(
                item,
                checkpoint,
                chain,
            )
        except Exception as exc:
            raise DurableArchiveStoreError(
                "archive failed live-chain verification: "
                f"{type(exc).__name__}"
            ) from exc
        if not verification.valid:
            raise DurableArchiveStoreError(
                "archive failed live-chain verification"
            )
        manifest = item.manifest
        if manifest.node_count > self.max_nodes_per_archive:
            raise DurableArchiveStoreError("archive node bound exceeded")
        prefix = chain.snapshot_at(manifest.checkpoint_root)
        if len(prefix) != manifest.node_count:
            raise DurableArchiveStoreError("archive prefix length differs from manifest")

        archived_nodes = tuple(
            self._encode_node(manifest.chain_id, node)
            for node in prefix
        )
        if tuple(node.node_hash for node in archived_nodes) != tuple(
            entry.node_hash for entry in manifest.entries
        ):
            raise DurableArchiveStoreError("archive node hashes differ from manifest")
        if tuple(node.object_digest for node in archived_nodes) != tuple(
            entry.object_digest for entry in manifest.entries
        ):
            raise DurableArchiveStoreError("archive object digests differ from manifest")

        for archived in archived_nodes:
            self._decode_node(archived)
            self._put_node(archived)

        existing_archive = self.get(
            manifest.archive_id
        )
        if existing_archive is not None:
            if (
                existing_archive.manifest != item
                or existing_archive.checkpoint != checkpoint
                or existing_archive.node_hashes
                != tuple(
                    node.node_hash
                    for node in archived_nodes
                )
            ):
                raise DurableArchiveStoreError(
                    "archive_id already binds incompatible archive state"
                )
            repaired_indexes = self.repair_indexes(
                manifest.archive_id
            )
            return DurableArchiveStoreReport(
                manifest.archive_id,
                manifest.chain_id,
                manifest.checkpoint_sequence,
                manifest.checkpoint_root,
                manifest.node_count,
                manifest.digest,
                checkpoint.checkpoint.digest,
                False,
                repaired_indexes,
            )

        now = self._clock()
        if (
            isinstance(now, bool)
            or not isinstance(now, (int, float))
            or not math.isfinite(float(now))
            or float(now) < 0.0
        ):
            raise DurableArchiveStoreError("archive store clock is invalid")
        node_hashes = tuple(
            node.node_hash
            for node in archived_nodes
        )
        record_digest = self._record_digest(
            manifest_digest=manifest.digest,
            checkpoint_digest=checkpoint.checkpoint.digest,
            node_hashes=node_hashes,
            stored_at=float(now),
        )
        record_value = {
            "manifest": item.to_dict(),
            "checkpoint": checkpoint.to_dict(),
            "node_hashes": list(node_hashes),
            "stored_at": float(now),
            "record_digest": record_digest,
        }
        archive_key = self._archive_key(manifest.archive_id)
        fresh_write = self._put_immutable(
            archive_key,
            record_value,
            conflict_message="archive_id already binds different archive payload",
        )
        archive_record = self.backend.get(self.namespace, archive_key)
        if archive_record is None:
            raise DurableArchiveStoreError("archive record missing after put")

        repaired_indexes = 0
        genesis_index = DurableArchiveRootIndex(
            manifest.chain_id,
            GENESIS_HASH,
            0,
            manifest.archive_id,
            manifest.digest,
        )
        if self._put_root_index(genesis_index):
            repaired_indexes += 1
        self._put_sequence_index(
            DurableArchiveSequenceIndex(
                manifest.chain_id,
                0,
                GENESIS_HASH,
            )
        )
        for archived in archived_nodes:
            index = DurableArchiveRootIndex(
                manifest.chain_id,
                archived.node_hash,
                archived.sequence,
                manifest.archive_id,
                manifest.digest,
            )
            if self._put_root_index(index):
                repaired_indexes += 1
            self._put_sequence_index(
                DurableArchiveSequenceIndex(
                    manifest.chain_id,
                    archived.sequence,
                    archived.node_hash,
                )
            )

        self._update_head(
            DurableArchiveHead(
                manifest.chain_id,
                manifest.checkpoint_sequence,
                manifest.checkpoint_root,
                manifest.archive_id,
                manifest.digest,
            )
        )
        return DurableArchiveStoreReport(
            manifest.archive_id,
            manifest.chain_id,
            manifest.checkpoint_sequence,
            manifest.checkpoint_root,
            manifest.node_count,
            manifest.digest,
            checkpoint.checkpoint.digest,
            fresh_write,
            repaired_indexes,
        )

    def _stored(
        self,
        revision: int,
        raw: dict[str, object],
    ) -> StoredDurableArchive:
        manifest_raw = raw.get("manifest")
        checkpoint_raw = raw.get("checkpoint")
        node_hashes_raw = raw.get("node_hashes", ())
        if not isinstance(manifest_raw, dict) or not isinstance(checkpoint_raw, dict):
            raise DurableArchiveStoreError("stored archive metadata shape invalid")
        if not isinstance(node_hashes_raw, (list, tuple)):
            raise DurableArchiveStoreError("stored archive node_hashes shape invalid")
        manifest = self._manifest(dict(manifest_raw))
        checkpoint = self._checkpoint(dict(checkpoint_raw))
        node_hashes = tuple(
            str(item)
            for item in node_hashes_raw
        )
        stored_at = float(raw["stored_at"])
        expected_record_digest = self._record_digest(
            manifest_digest=manifest.manifest.digest,
            checkpoint_digest=checkpoint.checkpoint.digest,
            node_hashes=node_hashes,
            stored_at=stored_at,
        )
        if str(raw.get("record_digest", "")) != expected_record_digest:
            raise DurableArchiveStoreError(
                "archive record digest mismatch"
            )
        stored = StoredDurableArchive(
            revision,
            manifest,
            checkpoint,
            node_hashes,
            stored_at,
        )
        self._verify_manifest_signature(manifest)
        self._verify_checkpoint_authority(checkpoint)
        if manifest.manifest.checkpoint_digest != checkpoint.checkpoint.digest:
            raise DurableArchiveStoreError("stored archive/checkpoint digest mismatch")
        if manifest.manifest.chain_id != checkpoint.checkpoint.chain_id:
            raise DurableArchiveStoreError("stored archive/checkpoint chain mismatch")
        if manifest.manifest.checkpoint_root != checkpoint.checkpoint.root_hash:
            raise DurableArchiveStoreError("stored archive/checkpoint root mismatch")
        return stored

    def get(
        self,
        archive_id: str,
    ) -> StoredDurableArchive | None:
        record = self.backend.get(
            self.namespace,
            self._archive_key(archive_id),
        )
        if record is None:
            return None
        if not isinstance(record.value, dict):
            raise DurableArchiveStoreError("archive record must be mapping")
        stored = self._stored(
            record.revision,
            dict(record.value),
        )
        if stored.manifest.manifest.archive_id != archive_id:
            raise DurableArchiveStoreError("archive record identity mismatch")
        return stored

    def require(
        self,
        archive_id: str,
    ) -> StoredDurableArchive:
        stored = self.get(archive_id)
        if stored is None:
            raise DurableArchiveStoreError("required archive is missing")
        self.verify_archive(stored)
        return stored

    def root_index(
        self,
        chain_id: str,
        root_hash: str,
    ) -> DurableArchiveRootIndex | None:
        record = self.backend.get(
            self.namespace,
            self._root_key(chain_id, root_hash),
        )
        if record is None:
            return None
        if not isinstance(record.value, dict):
            raise DurableArchiveStoreError("archive root index must be mapping")
        index = self._root_index(dict(record.value))
        if index.chain_id != chain_id or index.root_hash != root_hash:
            raise DurableArchiveStoreError("archive root index identity mismatch")
        return index

    def backfill_sequence_indexes_batch(
        self,
        chain_id: str,
        *,
        end_sequence: int | None = None,
        end_root: str = "",
        max_items: int = 1024,
    ) -> SequenceIndexBackfillBatch:
        _identity("chain_id", chain_id, maximum=128)
        if (
            isinstance(max_items, bool)
            or not isinstance(max_items, int)
            or max_items <= 0
        ):
            raise ValueError(
                "max_items must be positive integer"
            )
        head = self.latest(chain_id)
        if head is None:
            if end_sequence not in (None, 0):
                raise ValueError(
                    "archive backfill end_sequence exceeds empty archive"
                )
            if end_root and end_root != GENESIS_HASH:
                raise DurableArchiveStoreError(
                    "empty archive backfill root must be genesis"
                )
            return SequenceIndexBackfillBatch(
                0,
                GENESIS_HASH,
                None,
                None,
                0,
                0,
                0,
                GENESIS_HASH,
                True,
            )
        target = (
            head.sequence
            if end_sequence is None
            else end_sequence
        )
        if (
            isinstance(target, bool)
            or not isinstance(target, int)
            or target < 0
            or target > head.sequence
        ):
            raise ValueError(
                "archive backfill end_sequence outside archived range"
            )
        if target == 0:
            if end_root and end_root != GENESIS_HASH:
                raise DurableArchiveStoreError(
                    "zero-sequence archive backfill root must be genesis"
                )
            return SequenceIndexBackfillBatch(
                0,
                GENESIS_HASH,
                None,
                None,
                0,
                0,
                0,
                GENESIS_HASH,
                True,
            )

        stored = self.get(head.archive_id)
        if (
            stored is None
            or not self.verify_archive(stored)
        ):
            raise DurableArchiveStoreError(
                "archive backfill lacks verified head archive"
            )
        if target > len(stored.node_hashes):
            raise DurableArchiveStoreError(
                "archive backfill exceeds head archive payload"
            )
        expected_end_root = stored.node_hashes[
            target - 1
        ]
        if end_root:
            end_root = _digest(
                "end_root",
                end_root,
            )
            if end_root != expected_end_root:
                raise DurableArchiveStoreError(
                    "archive backfill root/sequence mismatch"
                )
        else:
            end_root = expected_end_root

        requested_end_sequence = target
        requested_end_root = end_root
        start = max(
            1,
            target - max_items + 1,
        )
        indexed = 0
        already_indexed = 0
        for sequence in range(
            target,
            start - 1,
            -1,
        ):
            expected_root = stored.node_hashes[
                sequence - 1
            ]
            entry = self.sequence_index(
                chain_id,
                sequence,
            )
            if entry is None:
                self._put_sequence_index(
                    DurableArchiveSequenceIndex(
                        chain_id,
                        sequence,
                        expected_root,
                    )
                )
                indexed += 1
            elif entry.root_hash != expected_root:
                raise DurableArchiveStoreError(
                    "archive backfill found conflicting sequence index"
                )
            else:
                already_indexed += 1

        next_sequence = start - 1
        next_root = (
            GENESIS_HASH
            if next_sequence == 0
            else stored.node_hashes[
                next_sequence - 1
            ]
        )
        return SequenceIndexBackfillBatch(
            requested_end_sequence,
            requested_end_root,
            start,
            requested_end_sequence,
            indexed,
            already_indexed,
            next_sequence,
            next_root,
            next_sequence == 0,
        )

    def inspect_sequence_indexes(
        self,
        chain_id: str,
        *,
        end_sequence: int | None = None,
        max_items: int = 100_000,
    ) -> DurableArchiveSequenceIndexHealth:
        _identity("chain_id", chain_id, maximum=128)
        if (
            isinstance(max_items, bool)
            or not isinstance(max_items, int)
            or max_items <= 0
        ):
            raise ValueError(
                "max_items must be positive integer"
            )
        head = self.latest(chain_id)
        if head is None:
            if end_sequence not in (None, 0):
                raise IndexError(
                    "archive sequence inspection exceeds empty archive"
                )
            return DurableArchiveSequenceIndexHealth(
                0,
                0,
                0,
                0,
                0,
            )
        target = (
            head.sequence
            if end_sequence is None
            else end_sequence
        )
        if (
            isinstance(target, bool)
            or not isinstance(target, int)
            or target < 0
            or target > head.sequence
        ):
            raise ValueError(
                "archive index inspection end_sequence outside archived range"
            )
        if target > max_items:
            raise DurableArchiveStoreError(
                "archive index inspection exceeds bounded window"
            )
        stored = self.get(head.archive_id)
        if (
            stored is None
            or not self.verify_archive(stored)
        ):
            raise DurableArchiveStoreError(
                "archive index inspection lacks verified head archive"
            )
        if target > len(stored.node_hashes):
            raise DurableArchiveStoreError(
                "archive index inspection exceeds head archive payload"
            )

        indexed = 0
        missing = 0
        corrupt = 0
        first_missing = None
        first_corrupt = None
        for sequence in range(1, target + 1):
            expected_root = stored.node_hashes[
                sequence - 1
            ]
            try:
                entry = self.sequence_index(
                    chain_id,
                    sequence,
                )
            except DurableArchiveStoreError:
                corrupt += 1
                if first_corrupt is None:
                    first_corrupt = sequence
                continue
            if entry is None:
                missing += 1
                if first_missing is None:
                    first_missing = sequence
                continue
            if entry.root_hash != expected_root:
                corrupt += 1
                if first_corrupt is None:
                    first_corrupt = sequence
                continue
            root_index = self.root_index(
                chain_id,
                expected_root,
            )
            if (
                root_index is None
                or root_index.sequence != sequence
            ):
                corrupt += 1
                if first_corrupt is None:
                    first_corrupt = sequence
                continue
            indexed += 1
        return DurableArchiveSequenceIndexHealth(
            head.sequence,
            target,
            indexed,
            missing,
            corrupt,
            first_missing,
            first_corrupt,
        )

    def repair_sequence_indexes(
        self,
        chain_id: str,
        *,
        end_sequence: int | None = None,
        max_items: int = 100_000,
    ) -> DurableArchiveSequenceIndexHealth:
        _identity("chain_id", chain_id, maximum=128)
        head = self.latest(chain_id)
        if head is None:
            return self.inspect_sequence_indexes(
                chain_id,
                end_sequence=end_sequence,
                max_items=max_items,
            )
        target = (
            head.sequence
            if end_sequence is None
            else end_sequence
        )
        if (
            isinstance(target, bool)
            or not isinstance(target, int)
            or target < 0
            or target > head.sequence
        ):
            raise ValueError(
                "archive index repair end_sequence outside archived range"
            )
        if target > max_items:
            raise DurableArchiveStoreError(
                "archive index repair exceeds bounded window"
            )
        stored = self.get(head.archive_id)
        if (
            stored is None
            or not self.verify_archive(stored)
        ):
            raise DurableArchiveStoreError(
                "archive index repair lacks verified head archive"
            )
        for sequence in range(1, target + 1):
            self._put_sequence_index(
                DurableArchiveSequenceIndex(
                    chain_id,
                    sequence,
                    stored.node_hashes[
                        sequence - 1
                    ],
                )
            )
        return self.inspect_sequence_indexes(
            chain_id,
            end_sequence=target,
            max_items=max_items,
        )

    def sequence_index(
        self,
        chain_id: str,
        sequence: int,
    ) -> DurableArchiveSequenceIndex | None:
        _identity("chain_id", chain_id, maximum=128)
        key = self._sequence_key(
            chain_id,
            sequence,
        )
        record = self.backend.get(
            self.namespace,
            key,
        )
        if record is None:
            return None
        if not isinstance(record.value, dict):
            raise DurableArchiveStoreError(
                "archive sequence index must be mapping"
            )
        index = self._sequence_index(
            dict(record.value)
        )
        if (
            index.chain_id != chain_id
            or index.sequence != sequence
        ):
            raise DurableArchiveStoreError(
                "archive sequence index identity mismatch"
            )
        return index

    def root_for_sequence(
        self,
        chain_id: str,
        sequence: int,
        *,
        repair_missing: bool = True,
    ) -> str:
        _identity("chain_id", chain_id, maximum=128)
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence < 0
        ):
            raise ValueError(
                "archive sequence must be non-negative integer"
            )
        if sequence == 0:
            return GENESIS_HASH
        head = self.latest(chain_id)
        if head is None:
            raise DurableArchiveStoreError(
                "archive chain has no committed head"
            )
        if sequence > head.sequence:
            raise IndexError(
                "archive sequence is beyond archived head"
            )
        index = self.sequence_index(
            chain_id,
            sequence,
        )
        if index is None:
            if not repair_missing:
                raise DurableArchiveStoreError(
                    "archive sequence index is missing"
                )
            stored = self.get(
                head.archive_id
            )
            if (
                stored is None
                or not self.verify_archive(stored)
            ):
                raise DurableArchiveStoreError(
                    "archive sequence index repair lacks verified head archive"
                )
            if sequence > len(stored.node_hashes):
                raise DurableArchiveStoreError(
                    "archive head does not contain requested sequence"
                )
            root_hash = stored.node_hashes[
                sequence - 1
            ]
            candidate = DurableArchiveSequenceIndex(
                chain_id,
                sequence,
                root_hash,
            )
            self._put_sequence_index(candidate)
            index = self.sequence_index(
                chain_id,
                sequence,
            )
            if index is None:
                raise DurableArchiveStoreError(
                    "archive sequence index repair did not persist"
                )
        root_index = self.root_index(
            chain_id,
            index.root_hash,
        )
        if root_index is None:
            raise DurableArchiveStoreError(
                "archive sequence index root is not indexed"
            )
        if root_index.sequence != sequence:
            raise DurableArchiveStoreError(
                "archive sequence/root index disagreement"
            )
        if not self.verify_root(
            chain_id,
            index.root_hash,
        ):
            raise DurableArchiveStoreError(
                "archive sequence index resolves unverifiable root"
            )
        return index.root_hash

    def get_by_sequence(
        self,
        chain_id: str,
        sequence: int,
        *,
        repair_missing: bool = True,
    ):
        root_hash = self.root_for_sequence(
            chain_id,
            sequence,
            repair_missing=repair_missing,
        )
        node = self.get_node(
            chain_id,
            root_hash,
        )
        if int(node.sequence) != sequence:
            raise DurableArchiveStoreError(
                "archive sequence index resolves wrong node sequence"
            )
        return node

    def latest(
        self,
        chain_id: str,
    ) -> DurableArchiveHead | None:
        record = self.backend.get(
            self.namespace,
            self._head_key(chain_id),
        )
        if record is None:
            return None
        if not isinstance(record.value, dict):
            raise DurableArchiveStoreError("archive head must be mapping")
        head = self._head(dict(record.value))
        if head.chain_id != chain_id:
            raise DurableArchiveStoreError("archive head identity mismatch")
        return head

    def get_node(
        self,
        chain_id: str,
        node_hash: str,
    ):
        record = self.backend.get(
            self.namespace,
            self._node_key(chain_id, node_hash),
        )
        if record is None:
            raise DurableArchiveStoreError("archived node is missing")
        if not isinstance(record.value, dict):
            raise DurableArchiveStoreError("archived node record must be mapping")
        archived = self._archived_node(dict(record.value))
        if archived.chain_id != chain_id or archived.node_hash != node_hash:
            raise DurableArchiveStoreError("archived node identity mismatch")
        return self._decode_node(archived)

    def _stored_nodes(
        self,
        stored: StoredDurableArchive,
        *,
        through_sequence: int | None = None,
    ) -> tuple[object, ...]:
        manifest = stored.manifest.manifest
        limit = (
            len(stored.node_hashes)
            if through_sequence is None
            else through_sequence
        )
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or limit < 0
            or limit > len(stored.node_hashes)
        ):
            raise DurableArchiveStoreError(
                "archive node reconstruction sequence outside stored range"
            )
        nodes = tuple(
            self.get_node(
                manifest.chain_id,
                node_hash,
            )
            for node_hash in stored.node_hashes[:limit]
        )
        previous = GENESIS_HASH
        for expected_sequence, node in enumerate(
            nodes,
            start=1,
        ):
            node_hash = str(
                getattr(
                    node,
                    "event_hash",
                    getattr(
                        node,
                        "receipt_hash",
                        getattr(
                            node,
                            "node_hash",
                            "",
                        ),
                    ),
                )
            )
            if int(node.sequence) != expected_sequence:
                raise DurableArchiveStoreError(
                    "archived snapshot sequence is not contiguous"
                )
            if str(node.previous_hash) != previous:
                raise DurableArchiveStoreError(
                    "archived snapshot previous hash is not contiguous"
                )
            previous = node_hash
        return nodes

    def resolve_root(
        self,
        chain_id: str,
        root_hash: str,
    ) -> DurableArchiveRootResolution:
        root_hash = _digest(
            "root_hash",
            root_hash,
        )
        index = self.root_index(
            chain_id,
            root_hash,
        )
        if index is None:
            raise DurableArchiveStoreError(
                "historical root is unavailable: not archived"
            )
        failures: list[str] = []
        for position, replica in enumerate(
            index.replicas
        ):
            try:
                stored = self.get(
                    replica.archive_id
                )
                if stored is None:
                    raise DurableArchiveStoreError(
                        "archive replica is missing"
                    )
                if (
                    stored.manifest.manifest.digest
                    != replica.archive_manifest_digest
                ):
                    raise DurableArchiveStoreError(
                        "root replica manifest digest mismatch"
                    )
                if (
                    index.sequence
                    > len(stored.node_hashes)
                ):
                    raise DurableArchiveStoreError(
                        "root index sequence exceeds archive replica"
                    )
                # Reconstruct the requested prefix before collapsing verification
                # to a boolean so missing/corrupt archived-node diagnostics remain
                # actionable to callers.
                nodes = self._stored_nodes(
                    stored,
                    through_sequence=(
                        index.sequence
                    ),
                )
                if not self.verify_archive(
                    stored
                ):
                    raise DurableArchiveStoreError(
                        "archive replica failed verification"
                    )
                terminal = (
                    GENESIS_HASH
                    if not nodes
                    else str(
                        getattr(
                            nodes[-1],
                            "event_hash",
                            getattr(
                                nodes[-1],
                                "receipt_hash",
                                getattr(
                                    nodes[-1],
                                    "node_hash",
                                    "",
                                ),
                            ),
                        )
                    )
                )
                if terminal != root_hash:
                    raise DurableArchiveStoreError(
                        "archive replica does not terminate at root"
                    )
                return DurableArchiveRootResolution(
                    chain_id,
                    root_hash,
                    index.sequence,
                    replica.archive_id,
                    replica.archive_manifest_digest,
                    position,
                )
            except Exception as exc:
                failures.append(
                    f"{replica.archive_id}:"
                    f"{type(exc).__name__}:"
                    f"{exc}"
                )
        raise DurableArchiveStoreError(
            "all archive replicas failed historical resolution: "
            + ",".join(failures)
        )

    def snapshot_at(
        self,
        chain_id: str,
        root_hash: str,
    ) -> tuple[object, ...]:
        root_hash = _digest(
            "root_hash",
            root_hash,
        )
        if root_hash == GENESIS_HASH:
            return ()
        resolution = self.resolve_root(
            chain_id,
            root_hash,
        )
        stored = self.get(
            resolution.archive_id
        )
        if stored is None:
            raise DurableArchiveStoreError(
                "resolved archive replica disappeared"
            )
        nodes = self._stored_nodes(
            stored,
            through_sequence=(
                resolution.sequence
            ),
        )
        terminal = str(
            getattr(
                nodes[-1],
                "event_hash",
                getattr(
                    nodes[-1],
                    "receipt_hash",
                    getattr(
                        nodes[-1],
                        "node_hash",
                        "",
                    ),
                ),
            )
        )
        if terminal != root_hash:
            raise DurableArchiveStoreError(
                "resolved archive replica changed during read"
            )
        return nodes

    def sequence_for_root(
        self,
        chain_id: str,
        root_hash: str,
    ) -> int:
        _identity("chain_id", chain_id, maximum=128)
        root_hash = _digest(
            "root_hash",
            root_hash,
        )
        if root_hash == GENESIS_HASH:
            return 0
        resolution = self.resolve_root(
            chain_id,
            root_hash,
        )
        return resolution.sequence

    def snapshot_segment(
        self,
        chain_id: str,
        start_exclusive_root: str,
        end_inclusive_root: str,
        *,
        max_items: int = 4096,
    ) -> tuple[object, ...]:
        """Verify and load only one bounded archived chain segment."""
        _identity("chain_id", chain_id, maximum=128)
        if (
            isinstance(max_items, bool)
            or not isinstance(max_items, int)
            or max_items <= 0
        ):
            raise ValueError("max_items must be positive integer")
        start_exclusive_root = _digest(
            "start_exclusive_root",
            start_exclusive_root,
        )
        end_inclusive_root = _digest(
            "end_inclusive_root",
            end_inclusive_root,
        )
        if (
            start_exclusive_root
            == end_inclusive_root
        ):
            return ()
        if end_inclusive_root == GENESIS_HASH:
            raise DurableArchiveStoreError(
                "archive segment end precedes non-genesis start"
            )

        index = self.root_index(
            chain_id,
            end_inclusive_root,
        )
        if index is None:
            raise DurableArchiveStoreError(
                "archive segment end root is not indexed"
            )

        failures: list[str] = []
        for replica in index.replicas:
            try:
                stored = self.get(
                    replica.archive_id
                )
                if stored is None:
                    raise DurableArchiveStoreError(
                        "archive segment replica is missing"
                    )
                manifest = stored.manifest.manifest
                if manifest.chain_id != chain_id:
                    raise DurableArchiveStoreError(
                        "archive segment chain mismatch"
                    )
                if (
                    manifest.digest
                    != replica.archive_manifest_digest
                ):
                    raise DurableArchiveStoreError(
                        "archive segment replica manifest mismatch"
                    )

                try:
                    end_position = (
                        stored.node_hashes.index(
                            end_inclusive_root
                        )
                        + 1
                    )
                except ValueError as exc:
                    raise DurableArchiveStoreError(
                        "archive segment end root is absent from replica"
                    ) from exc
                if index.sequence != end_position:
                    raise DurableArchiveStoreError(
                        "archive root index sequence differs from signed replica"
                    )

                if start_exclusive_root == GENESIS_HASH:
                    start_position = 0
                else:
                    try:
                        start_position = (
                            stored.node_hashes.index(
                                start_exclusive_root,
                                0,
                                end_position,
                            )
                            + 1
                        )
                    except ValueError as exc:
                        raise DurableArchiveStoreError(
                            "archive segment start root is not an ancestor "
                            "inside replica"
                        ) from exc

                if end_position < start_position:
                    raise DurableArchiveStoreError(
                        "archive segment end precedes start"
                    )
                distance = (
                    end_position - start_position
                )
                if distance > max_items:
                    raise DurableArchiveStoreError(
                        "archive segment exceeds bounded verification window"
                    )
                if distance == 0:
                    raise DurableArchiveStoreError(
                        "archive segment roots differ at equal position"
                    )

                hashes = stored.node_hashes[
                    start_position:end_position
                ]
                signed_entries = manifest.entries[
                    start_position:end_position
                ]
                if (
                    len(hashes) != distance
                    or len(signed_entries) != distance
                ):
                    raise DurableArchiveStoreError(
                        "archive segment metadata length mismatch"
                    )

                nodes: list[object] = []
                previous = start_exclusive_root
                expected_sequence = start_position + 1
                for (
                    node_hash,
                    signed_entry,
                ) in zip(
                    hashes,
                    signed_entries,
                    strict=True,
                ):
                    node = self.get_node(
                        chain_id,
                        node_hash,
                    )
                    encoded = self._encode_node(
                        chain_id,
                        node,
                    )
                    if (
                        encoded.sequence
                        != expected_sequence
                        or encoded.previous_hash
                        != previous
                        or encoded.node_hash
                        != node_hash
                    ):
                        raise DurableArchiveStoreError(
                            "archive segment native linkage mismatch"
                        )
                    kind = (
                        str(
                            encoded.payload.get(
                                "kind",
                                "execution.receipt",
                            )
                        )
                        if encoded.node_type
                        is not DurableArchivedNodeType.EXECUTION_RECEIPT
                        else "execution.receipt"
                    )
                    actual_entry = DurableArchiveEntry(
                        encoded.sequence,
                        encoded.previous_hash,
                        encoded.node_hash,
                        kind,
                        encoded.object_digest,
                    )
                    if actual_entry != signed_entry:
                        raise DurableArchiveStoreError(
                            "archive segment node differs from signed manifest"
                        )
                    nodes.append(node)
                    previous = encoded.node_hash
                    expected_sequence += 1

                if previous != end_inclusive_root:
                    raise DurableArchiveStoreError(
                        "archive segment terminal root mismatch"
                    )
                return tuple(nodes)
            except Exception as exc:
                failures.append(
                    f"{replica.archive_id}:"
                    f"{type(exc).__name__}"
                )

        raise DurableArchiveStoreError(
            "all archive replicas failed bounded segment resolution: "
            + ",".join(failures)
        )

    def verify_root(
        self,
        chain_id: str,
        root_hash: str,
    ) -> bool:
        try:
            nodes = self.snapshot_at(chain_id, root_hash)
        except (
            DurableArchiveStoreError,
            ValueError,
            TypeError,
            KeyError,
        ):
            return False
        if root_hash == GENESIS_HASH:
            return nodes == ()
        if not nodes:
            return False
        terminal = nodes[-1]
        terminal_hash = str(
            getattr(
                terminal,
                "event_hash",
                getattr(
                    terminal,
                    "receipt_hash",
                    getattr(terminal, "node_hash", ""),
                ),
            )
        )
        return terminal_hash == root_hash

    def root_is_archived(
        self,
        chain_id: str,
        root_hash: str,
    ) -> bool:
        if root_hash == GENESIS_HASH:
            return self.latest(chain_id) is not None
        return (
            self.root_index(chain_id, root_hash) is not None
            and self.verify_root(chain_id, root_hash)
        )

    def verify_archive(
        self,
        stored: StoredDurableArchive,
    ) -> bool:
        manifest = stored.manifest.manifest
        try:
            self._verify_manifest_signature(stored.manifest)
            self._verify_checkpoint_authority(stored.checkpoint)
            nodes = self._stored_nodes(
                stored,
                through_sequence=manifest.checkpoint_sequence,
            )
            terminal = (
                GENESIS_HASH
                if not nodes
                else str(
                    getattr(
                        nodes[-1],
                        "event_hash",
                        getattr(
                            nodes[-1],
                            "receipt_hash",
                            getattr(
                                nodes[-1],
                                "node_hash",
                                "",
                            ),
                        ),
                    )
                )
            )
            if terminal != manifest.checkpoint_root:
                return False
            encoded = tuple(
                self._encode_node(manifest.chain_id, node)
                for node in nodes
            )
            entries = tuple(
                DurableArchiveEntry(
                    item.sequence,
                    item.previous_hash,
                    item.node_hash,
                    (
                        str(item.payload.get("kind", "execution.receipt"))
                        if item.node_type is not DurableArchivedNodeType.EXECUTION_RECEIPT
                        else "execution.receipt"
                    ),
                    item.object_digest,
                )
                for item in encoded
            )
            return (
                len(nodes) == manifest.node_count
                and tuple(item.node_hash for item in encoded) == stored.node_hashes
                and entries == manifest.entries
                and DurableArchiveManifest.compute_entries_digest(entries)
                == manifest.entries_digest
            )
        except (
            DurableArchiveStoreError,
            ArtifactSignatureError,
            ValueError,
            TypeError,
            KeyError,
        ):
            return False

    def inspect_indexes(
        self,
        archive_id: str,
    ) -> DurableArchiveIndexHealth:
        _identity(
            "archive_id",
            archive_id,
            maximum=160,
        )
        stored = self.get(
            archive_id
        )
        if stored is None:
            raise DurableArchiveStoreError(
                "required archive is missing"
            )
        manifest = stored.manifest.manifest
        if not self.verify_archive(
            stored
        ):
            return DurableArchiveIndexHealth(
                archive_id,
                manifest.chain_id,
                DurableArchiveIndexState.INVALID,
                False,
                manifest.node_count + 1,
                0,
                0,
                (),
                (),
                (),
                False,
                True,
            )

        expected = (
            (GENESIS_HASH, 0),
            *tuple(
                (
                    node_hash,
                    sequence,
                )
                for sequence, node_hash
                in enumerate(
                    stored.node_hashes,
                    start=1,
                )
            ),
        )
        missing_root: list[str] = []
        missing_replica: list[str] = []
        corrupt_root: list[str] = []
        root_present = 0
        replica_present = 0

        for (
            root_hash,
            sequence,
        ) in expected:
            key = self._root_key(
                manifest.chain_id,
                root_hash,
            )
            record = self.backend.get(
                self.namespace,
                key,
            )
            if record is None:
                missing_root.append(
                    root_hash
                )
                continue
            root_present += 1
            if not isinstance(
                record.value,
                dict,
            ):
                corrupt_root.append(
                    root_hash
                )
                continue
            try:
                index = self._root_index(
                    dict(record.value)
                )
            except Exception:
                corrupt_root.append(
                    root_hash
                )
                continue
            if (
                index.chain_id
                != manifest.chain_id
                or index.root_hash
                != root_hash
                or index.sequence
                != sequence
            ):
                corrupt_root.append(
                    root_hash
                )
                continue
            matching = tuple(
                replica
                for replica in index.replicas
                if (
                    replica.archive_id
                    == archive_id
                )
            )
            if not matching:
                missing_replica.append(
                    root_hash
                )
                continue
            if (
                len(matching) != 1
                or matching[0]
                .archive_manifest_digest
                != manifest.digest
            ):
                corrupt_root.append(
                    root_hash
                )
                continue
            replica_present += 1

        head_repair_required = False
        head_valid = True
        head_record = self.backend.get(
            self.namespace,
            self._head_key(
                manifest.chain_id
            ),
        )
        if head_record is None:
            head_repair_required = True
        elif not isinstance(
            head_record.value,
            dict,
        ):
            head_valid = False
        else:
            try:
                head = self._head(
                    dict(
                        head_record.value
                    )
                )
            except Exception:
                head_valid = False
            else:
                if (
                    head.chain_id
                    != manifest.chain_id
                ):
                    head_valid = False
                elif (
                    head.sequence
                    < manifest.checkpoint_sequence
                ):
                    head_repair_required = True
                elif (
                    head.sequence
                    == manifest.checkpoint_sequence
                    and (
                        head.root_hash
                        != manifest.checkpoint_root
                        or head.archive_id
                        != archive_id
                        or head.archive_manifest_digest
                        != manifest.digest
                    )
                ):
                    head_valid = False

        if (
            corrupt_root
            or not head_valid
        ):
            state = (
                DurableArchiveIndexState.INVALID
            )
        elif (
            missing_root
            or missing_replica
            or head_repair_required
        ):
            state = (
                DurableArchiveIndexState.DEGRADED
            )
        else:
            state = (
                DurableArchiveIndexState.HEALTHY
            )

        return DurableArchiveIndexHealth(
            archive_id,
            manifest.chain_id,
            state,
            True,
            len(expected),
            root_present,
            replica_present,
            tuple(missing_root),
            tuple(missing_replica),
            tuple(corrupt_root),
            head_repair_required,
            head_valid,
        )

    def repair_indexes(
        self,
        archive_id: str,
    ) -> int:
        stored = self.get(archive_id)
        if stored is None:
            raise DurableArchiveStoreError(
                "required archive is missing"
            )
        if not self.verify_archive(stored):
            raise DurableArchiveStoreError(
                "archive failed verification before index repair"
            )
        manifest = stored.manifest.manifest
        repaired = 0
        genesis = DurableArchiveRootIndex(
            manifest.chain_id,
            GENESIS_HASH,
            0,
            manifest.archive_id,
            manifest.digest,
        )
        if self._put_root_index(genesis):
            repaired += 1
        self._put_sequence_index(
            DurableArchiveSequenceIndex(
                manifest.chain_id,
                0,
                GENESIS_HASH,
            )
        )
        for sequence, node_hash in enumerate(stored.node_hashes, start=1):
            index = DurableArchiveRootIndex(
                manifest.chain_id,
                node_hash,
                sequence,
                manifest.archive_id,
                manifest.digest,
            )
            if self._put_root_index(index):
                repaired += 1
            self._put_sequence_index(
                DurableArchiveSequenceIndex(
                    manifest.chain_id,
                    sequence,
                    node_hash,
                )
            )
        self._update_head(
            DurableArchiveHead(
                manifest.chain_id,
                manifest.checkpoint_sequence,
                manifest.checkpoint_root,
                manifest.archive_id,
                manifest.digest,
            )
        )
        return repaired


class ArchiveBackedHistoricalChain:
    """Logical full-chain reader over compacted hot storage plus archive.

    When the live chain has no active hot floor, reads delegate to the live
    chain exactly as before.  Once a signed hot floor becomes active, the
    archived prefix through that floor is treated as immutable history and the
    live chain supplies only the suffix after the floor.

    This wrapper is intentionally read-only.  It satisfies the durable
    checkpoint/archive read protocol without becoming an execution or mutation
    authority.
    """

    def __init__(
        self,
        chain_id: str,
        live_chain: CheckpointableEvidenceChain,
        archives: DurableArchiveRepository,
    ) -> None:
        _identity("chain_id", chain_id, maximum=128)
        if not isinstance(live_chain, CheckpointableEvidenceChain):
            raise TypeError("live_chain must satisfy CheckpointableEvidenceChain")
        if not isinstance(archives, DurableArchiveRepository):
            raise TypeError("archives must be DurableArchiveRepository")
        self.chain_id = chain_id
        self.live_chain = live_chain
        self.archives = archives

    @staticmethod
    def _node_hash(item: object) -> str:
        value = getattr(
            item,
            "event_hash",
            getattr(
                item,
                "receipt_hash",
                getattr(item, "node_hash", ""),
            ),
        )
        return str(value)

    @staticmethod
    def _node_sequence(item: object) -> int:
        return int(getattr(item, "sequence"))

    @staticmethod
    def _previous_hash(item: object) -> str:
        return str(getattr(item, "previous_hash"))

    def _active_floor(self):
        floor_method = getattr(
            self.live_chain,
            "hot_floor",
            None,
        )
        active_method = getattr(
            self.live_chain,
            "_hot_floor_active",
            None,
        )
        if not (
            callable(floor_method)
            and callable(active_method)
        ):
            return None
        floor = floor_method()
        if (
            int(getattr(floor, "sequence", 0))
            <= 0
        ):
            return None
        if not bool(active_method(floor)):
            return None
        if (
            not self.archives.verify_root(
                self.chain_id,
                str(floor.root_hash),
            )
        ):
            raise DurableArchiveStoreError(
                "active hot floor is not covered by a verified archive"
            )
        return floor

    def _archive_prefix(
        self,
        floor,
    ) -> tuple[object, ...]:
        prefix = tuple(
            self.archives.snapshot_at(
                self.chain_id,
                str(floor.root_hash),
            )
        )
        if len(prefix) != int(floor.sequence):
            raise DurableArchiveStoreError(
                "archive prefix length differs from active hot floor sequence"
            )
        if not prefix:
            raise DurableArchiveStoreError(
                "non-genesis active hot floor resolved empty archive prefix"
            )
        if (
            self._node_hash(prefix[-1])
            != str(floor.root_hash)
            or self._node_sequence(prefix[-1])
            != int(floor.sequence)
        ):
            raise DurableArchiveStoreError(
                "archive prefix terminal node differs from active hot floor"
            )
        return prefix

    def _verify_splice(
        self,
        floor,
        prefix: tuple[object, ...],
        suffix: tuple[object, ...],
    ) -> None:
        if not prefix:
            raise DurableArchiveStoreError(
                "hot/cold splice requires archive prefix"
            )
        if (
            self._node_hash(prefix[-1])
            != str(floor.root_hash)
            or self._node_sequence(prefix[-1])
            != int(floor.sequence)
        ):
            raise DurableArchiveStoreError(
                "hot/cold splice archive boundary mismatch"
            )
        if not suffix:
            return
        first = suffix[0]
        if (
            self._node_sequence(first)
            != int(floor.sequence) + 1
            or self._previous_hash(first)
            != str(floor.root_hash)
        ):
            raise DurableArchiveStoreError(
                "hot/cold splice live suffix does not continue archive floor"
            )
        expected_sequence = int(floor.sequence) + 1
        previous = str(floor.root_hash)
        for item in suffix:
            if (
                self._node_sequence(item)
                != expected_sequence
                or self._previous_hash(item)
                != previous
            ):
                raise DurableArchiveStoreError(
                    "hot/cold splice live suffix is not contiguous"
                )
            previous = self._node_hash(item)
            expected_sequence += 1

    def head(self):
        return self.live_chain.head()

    def verify(self) -> bool:
        try:
            if not bool(self.live_chain.verify()):
                return False
            floor = self._active_floor()
            if floor is None:
                return True
            prefix = self._archive_prefix(floor)
            suffix = tuple(self.live_chain.snapshot())
            self._verify_splice(
                floor,
                prefix,
                suffix,
            )
            head = self.live_chain.head()
            return (
                int(head.sequence)
                == len(prefix) + len(suffix)
                and (
                    str(head.root_hash)
                    == (
                        self._node_hash(suffix[-1])
                        if suffix
                        else str(floor.root_hash)
                    )
                )
            )
        except Exception:
            return False

    def snapshot(self):
        floor = self._active_floor()
        if floor is None:
            return self.live_chain.snapshot()
        prefix = self._archive_prefix(floor)
        suffix = tuple(
            self.live_chain.snapshot()
        )
        self._verify_splice(
            floor,
            prefix,
            suffix,
        )
        return prefix + suffix

    def root_hash(self) -> str:
        if hasattr(self.live_chain, "root_hash"):
            return str(self.live_chain.root_hash())
        return str(self.live_chain.head().root_hash)

    def length(self) -> int:
        return int(self.live_chain.head().sequence)

    def _sequence_for_root_live_or_archive(
        self,
        root_hash: str,
    ) -> int:
        root_hash = _digest(
            "root_hash",
            root_hash,
        )
        if root_hash == GENESIS_HASH:
            return 0
        live_sequence = getattr(
            self.live_chain,
            "sequence_for_root",
            None,
        )
        if callable(live_sequence):
            try:
                return int(
                    live_sequence(root_hash)
                )
            except Exception:
                pass
        return self.archives.sequence_for_root(
            self.chain_id,
            root_hash,
        )

    def snapshot_at(
        self,
        root_hash: str,
    ):
        root_hash = _digest(
            "root_hash",
            root_hash,
        )
        if root_hash == GENESIS_HASH:
            return ()
        floor = self._active_floor()
        if floor is None:
            try:
                return self.live_chain.snapshot_at(
                    root_hash
                )
            except Exception as live_error:
                try:
                    return self.archives.snapshot_at(
                        self.chain_id,
                        root_hash,
                    )
                except Exception as archive_error:
                    raise DurableArchiveStoreError(
                        "historical root unavailable from live chain and archive: "
                        f"{type(live_error).__name__}/"
                        f"{type(archive_error).__name__}"
                    ) from archive_error

        target_sequence = (
            self._sequence_for_root_live_or_archive(
                root_hash
            )
        )
        if target_sequence <= int(floor.sequence):
            return self.archives.snapshot_at(
                self.chain_id,
                root_hash,
            )

        prefix = self._archive_prefix(
            floor
        )
        try:
            suffix = tuple(
                self.live_chain.snapshot_at(
                    root_hash
                )
            )
        except Exception as exc:
            raise DurableArchiveStoreError(
                "live suffix for archive-backed historical root is unavailable: "
                f"{type(exc).__name__}"
            ) from exc
        self._verify_splice(
            floor,
            prefix,
            suffix,
        )
        if (
            not suffix
            or self._node_hash(suffix[-1])
            != root_hash
            or self._node_sequence(suffix[-1])
            != target_sequence
        ):
            raise DurableArchiveStoreError(
                "archive-backed historical suffix terminal root mismatch"
            )
        return prefix + suffix

    def root_for_sequence(
        self,
        sequence: int,
        *,
        repair_missing: bool = True,
    ) -> str:
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence < 0
        ):
            raise ValueError(
                "historical sequence must be non-negative integer"
            )
        if sequence == 0:
            return GENESIS_HASH
        head = self.head()
        if sequence > int(head.sequence):
            raise IndexError(
                "historical sequence is beyond committed head"
            )
        floor = self._active_floor()
        if floor is None:
            live_method = getattr(
                self.live_chain,
                "root_for_sequence",
                None,
            )
            if callable(live_method):
                return str(
                    live_method(
                        sequence,
                        repair_missing=repair_missing,
                    )
                )
            return self.archives.root_for_sequence(
                self.chain_id,
                sequence,
                repair_missing=repair_missing,
            )
        if sequence <= int(floor.sequence):
            return self.archives.root_for_sequence(
                self.chain_id,
                sequence,
                repair_missing=repair_missing,
            )
        live_method = getattr(
            self.live_chain,
            "root_for_sequence",
            None,
        )
        if not callable(live_method):
            raise DurableArchiveStoreError(
                "live chain does not support indexed root lookup"
            )
        root_hash = str(
            live_method(
                sequence,
                repair_missing=repair_missing,
            )
        )
        if sequence == int(floor.sequence) + 1:
            node = self.live_chain.get_by_sequence(
                sequence,
                repair_missing=repair_missing,
            )
            if self._previous_hash(node) != str(
                floor.root_hash
            ):
                raise DurableArchiveStoreError(
                    "live indexed sequence does not continue archive floor"
                )
        return root_hash

    def get_by_sequence(
        self,
        sequence: int,
        *,
        repair_missing: bool = True,
    ):
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence <= 0
        ):
            raise ValueError(
                "historical sequence must be positive integer"
            )
        head = self.head()
        if sequence > int(head.sequence):
            raise IndexError(
                "historical sequence is beyond committed head"
            )
        floor = self._active_floor()
        if floor is not None and sequence <= int(
            floor.sequence
        ):
            node = self.archives.get_by_sequence(
                self.chain_id,
                sequence,
                repair_missing=repair_missing,
            )
        else:
            live_method = getattr(
                self.live_chain,
                "get_by_sequence",
                None,
            )
            if callable(live_method):
                try:
                    node = live_method(
                        sequence,
                        repair_missing=repair_missing,
                    )
                except Exception as live_error:
                    if floor is not None:
                        raise DurableArchiveStoreError(
                            "live indexed historical lookup failed above floor: "
                            f"{type(live_error).__name__}"
                        ) from live_error
                    raise
            else:
                node = self.archives.get_by_sequence(
                    self.chain_id,
                    sequence,
                    repair_missing=repair_missing,
                )
        if self._node_sequence(node) != sequence:
            raise DurableArchiveStoreError(
                "historical indexed lookup returned wrong sequence"
            )
        expected_root = self.root_for_sequence(
            sequence,
            repair_missing=repair_missing,
        )
        if self._node_hash(node) != expected_root:
            raise DurableArchiveStoreError(
                "historical indexed lookup root mismatch"
            )
        return node

    def snapshot_range(
        self,
        start_sequence: int,
        end_sequence: int,
        *,
        max_items: int = 4096,
        repair_missing: bool = True,
    ):
        if (
            isinstance(start_sequence, bool)
            or not isinstance(start_sequence, int)
            or start_sequence <= 0
        ):
            raise ValueError(
                "start_sequence must be positive integer"
            )
        if (
            isinstance(end_sequence, bool)
            or not isinstance(end_sequence, int)
            or end_sequence < start_sequence
        ):
            raise ValueError(
                "end_sequence must be >= start_sequence"
            )
        if (
            isinstance(max_items, bool)
            or not isinstance(max_items, int)
            or max_items <= 0
        ):
            raise ValueError(
                "max_items must be positive integer"
            )
        count = end_sequence - start_sequence + 1
        if count > max_items:
            raise DurableArchiveStoreError(
                "historical range exceeds bounded verification window"
            )
        head = self.head()
        if end_sequence > int(head.sequence):
            raise IndexError(
                "historical range extends beyond committed head"
            )
        start_root = self.root_for_sequence(
            start_sequence - 1,
            repair_missing=repair_missing,
        )
        end_root = self.root_for_sequence(
            end_sequence,
            repair_missing=repair_missing,
        )
        items = tuple(
            self.snapshot_segment(
                start_root,
                end_root,
                max_items=max_items,
            )
        )
        if len(items) != count:
            raise DurableArchiveStoreError(
                "historical indexed range length mismatch"
            )
        expected_sequence = start_sequence
        previous = start_root
        for item in items:
            if (
                self._node_sequence(item)
                != expected_sequence
                or self._previous_hash(item)
                != previous
            ):
                raise DurableArchiveStoreError(
                    "historical indexed range is not contiguous"
                )
            previous = self._node_hash(item)
            expected_sequence += 1
        if previous != end_root:
            raise DurableArchiveStoreError(
                "historical indexed range terminal root mismatch"
            )
        return items

    def backfill_sequence_indexes_batch(
        self,
        *,
        end_sequence: int | None = None,
        end_root: str = "",
        max_items: int = 1024,
    ) -> SequenceIndexBackfillBatch:
        if (
            isinstance(max_items, bool)
            or not isinstance(max_items, int)
            or max_items <= 0
        ):
            raise ValueError(
                "max_items must be positive integer"
            )
        head = self.head()
        target = (
            int(head.sequence)
            if end_sequence is None
            else end_sequence
        )
        if (
            isinstance(target, bool)
            or not isinstance(target, int)
            or target < 0
            or target > int(head.sequence)
        ):
            raise ValueError(
                "historical backfill end_sequence outside committed range"
            )
        if target == 0:
            if end_root and end_root != GENESIS_HASH:
                raise DurableArchiveStoreError(
                    "zero-sequence historical backfill root must be genesis"
                )
            return SequenceIndexBackfillBatch(
                0,
                GENESIS_HASH,
                None,
                None,
                0,
                0,
                0,
                GENESIS_HASH,
                True,
            )
        if not end_root:
            if target != int(head.sequence):
                raise ValueError(
                    "historical backfill requires explicit root for non-head sequence"
                )
            end_root = str(head.root_hash)
        end_root = _digest(
            "end_root",
            end_root,
        )
        if (
            self._sequence_for_root_live_or_archive(
                end_root
            )
            != target
        ):
            raise DurableArchiveStoreError(
                "historical backfill root/sequence mismatch"
            )

        floor = self._active_floor()
        if floor is None:
            live_backfill = getattr(
                self.live_chain,
                "backfill_sequence_indexes_batch",
                None,
            )
            if callable(live_backfill):
                return live_backfill(
                    end_sequence=target,
                    end_root=end_root,
                    max_items=max_items,
                )
            return self.archives.backfill_sequence_indexes_batch(
                self.chain_id,
                end_sequence=target,
                end_root=end_root,
                max_items=max_items,
            )

        floor_sequence = int(floor.sequence)
        floor_root = str(floor.root_hash)
        if target <= floor_sequence:
            return self.archives.backfill_sequence_indexes_batch(
                self.chain_id,
                end_sequence=target,
                end_root=end_root,
                max_items=max_items,
            )

        live_budget = min(
            max_items,
            target - floor_sequence,
        )
        live_batch = (
            self.live_chain
            .backfill_sequence_indexes_batch(
                end_sequence=target,
                end_root=end_root,
                max_items=live_budget,
            )
        )
        if live_batch.next_sequence > floor_sequence:
            return live_batch
        if live_batch.next_sequence < floor_sequence:
            raise DurableArchiveStoreError(
                "live sequence-index backfill crossed trusted hot floor"
            )
        if live_batch.next_root != floor_root:
            raise DurableArchiveStoreError(
                "live sequence-index backfill did not terminate at hot floor"
            )
        remaining = (
            max_items - live_batch.covered_items
        )
        if remaining <= 0:
            return live_batch

        cold_batch = (
            self.archives
            .backfill_sequence_indexes_batch(
                self.chain_id,
                end_sequence=floor_sequence,
                end_root=floor_root,
                max_items=remaining,
            )
        )
        return SequenceIndexBackfillBatch(
            live_batch.requested_end_sequence,
            live_batch.requested_end_root,
            cold_batch.covered_start_sequence,
            live_batch.requested_end_sequence,
            live_batch.indexed + cold_batch.indexed,
            (
                live_batch.already_indexed
                + cold_batch.already_indexed
            ),
            cold_batch.next_sequence,
            cold_batch.next_root,
            cold_batch.complete_to_genesis,
        )

    @staticmethod
    def _merge_index_health(
        head_sequence: int,
        *reports,
    ) -> DurableArchiveSequenceIndexHealth:
        inspected = sum(
            int(item.inspected)
            for item in reports
        )
        indexed = sum(
            int(item.indexed)
            for item in reports
        )
        missing = sum(
            int(item.missing)
            for item in reports
        )
        corrupt = sum(
            int(item.corrupt)
            for item in reports
        )
        first_missing_candidates = tuple(
            int(item.first_missing_sequence)
            for item in reports
            if item.first_missing_sequence is not None
        )
        first_corrupt_candidates = tuple(
            int(item.first_corrupt_sequence)
            for item in reports
            if item.first_corrupt_sequence is not None
        )
        return DurableArchiveSequenceIndexHealth(
            head_sequence,
            inspected,
            indexed,
            missing,
            corrupt,
            (
                min(first_missing_candidates)
                if first_missing_candidates
                else None
            ),
            (
                min(first_corrupt_candidates)
                if first_corrupt_candidates
                else None
            ),
        )

    def inspect_sequence_indexes(
        self,
        *,
        max_items: int = 100_000,
    ) -> DurableArchiveSequenceIndexHealth:
        if (
            isinstance(max_items, bool)
            or not isinstance(max_items, int)
            or max_items <= 0
        ):
            raise ValueError(
                "max_items must be positive integer"
            )
        head = self.head()
        total = int(head.sequence)
        if total > max_items:
            raise DurableArchiveStoreError(
                "archive-backed index inspection exceeds bounded window"
            )
        floor = self._active_floor()
        if floor is None:
            live_inspect = getattr(
                self.live_chain,
                "inspect_sequence_indexes",
                None,
            )
            if callable(live_inspect):
                return live_inspect(
                    max_items=max_items,
                )
            archive_head = self.archives.latest(
                self.chain_id
            )
            if (
                archive_head is not None
                and archive_head.sequence == total
            ):
                return self.archives.inspect_sequence_indexes(
                    self.chain_id,
                    end_sequence=total,
                    max_items=max_items,
                )
            raise DurableArchiveStoreError(
                "historical chain has no sequence-index inspection surface"
            )

        floor_sequence = int(floor.sequence)
        archive_health = (
            self.archives.inspect_sequence_indexes(
                self.chain_id,
                end_sequence=floor_sequence,
                max_items=max_items,
            )
        )
        live_health = (
            self.live_chain.inspect_sequence_indexes(
                max_items=max(
                    1,
                    max_items - floor_sequence,
                ),
            )
        )
        return self._merge_index_health(
            total,
            archive_health,
            live_health,
        )

    def repair_sequence_indexes(
        self,
        *,
        max_items: int = 100_000,
    ) -> DurableArchiveSequenceIndexHealth:
        if (
            isinstance(max_items, bool)
            or not isinstance(max_items, int)
            or max_items <= 0
        ):
            raise ValueError(
                "max_items must be positive integer"
            )
        head = self.head()
        total = int(head.sequence)
        if total > max_items:
            raise DurableArchiveStoreError(
                "archive-backed index repair exceeds bounded window"
            )
        floor = self._active_floor()
        if floor is None:
            live_repair = getattr(
                self.live_chain,
                "repair_sequence_indexes",
                None,
            )
            if callable(live_repair):
                return live_repair(
                    max_items=max_items,
                )
            archive_head = self.archives.latest(
                self.chain_id
            )
            if (
                archive_head is not None
                and archive_head.sequence == total
            ):
                return self.archives.repair_sequence_indexes(
                    self.chain_id,
                    end_sequence=total,
                    max_items=max_items,
                )
            raise DurableArchiveStoreError(
                "historical chain has no sequence-index repair surface"
            )

        floor_sequence = int(floor.sequence)
        self.archives.repair_sequence_indexes(
            self.chain_id,
            end_sequence=floor_sequence,
            max_items=max_items,
        )
        self.live_chain.repair_sequence_indexes(
            max_items=max(
                1,
                max_items - floor_sequence,
            ),
        )
        return self.inspect_sequence_indexes(
            max_items=max_items,
        )

    def sequence_for_root(
        self,
        root_hash: str,
    ) -> int:
        return self._sequence_for_root_live_or_archive(
            root_hash
        )

    def snapshot_segment(
        self,
        start_exclusive_root: str,
        end_inclusive_root: str = "",
        *,
        max_items: int = 4096,
    ):
        """Resolve a bounded segment, including segments crossing hot/cold."""

        if (
            isinstance(max_items, bool)
            or not isinstance(max_items, int)
            or max_items <= 0
        ):
            raise ValueError(
                "max_items must be positive integer"
            )
        start_exclusive_root = _digest(
            "start_exclusive_root",
            start_exclusive_root,
        )
        end_inclusive_root = _digest(
            "end_inclusive_root",
            end_inclusive_root
            or self.root_hash(),
        )
        start_sequence = (
            self._sequence_for_root_live_or_archive(
                start_exclusive_root
            )
        )
        end_sequence = (
            self._sequence_for_root_live_or_archive(
                end_inclusive_root
            )
        )
        if end_sequence < start_sequence:
            raise DurableArchiveStoreError(
                "historical segment end precedes start"
            )
        distance = (
            end_sequence - start_sequence
        )
        if distance > max_items:
            raise DurableArchiveStoreError(
                "historical segment exceeds bounded verification window"
            )
        if distance == 0:
            if (
                start_exclusive_root
                != end_inclusive_root
            ):
                raise DurableArchiveStoreError(
                    "equal historical segment sequence has different roots"
                )
            return ()

        floor = self._active_floor()
        if floor is None:
            live_segment = getattr(
                self.live_chain,
                "snapshot_segment",
                None,
            )
            live_error: Exception | None = None
            if callable(live_segment):
                try:
                    return live_segment(
                        start_exclusive_root,
                        end_inclusive_root,
                        max_items=max_items,
                    )
                except Exception as exc:
                    live_error = exc
            try:
                return self.archives.snapshot_segment(
                    self.chain_id,
                    start_exclusive_root,
                    end_inclusive_root,
                    max_items=max_items,
                )
            except Exception as archive_error:
                raise DurableArchiveStoreError(
                    "bounded historical segment unavailable from live chain "
                    "and archive: "
                    f"{type(live_error).__name__ if live_error else 'unsupported'}/"
                    f"{type(archive_error).__name__}"
                ) from archive_error

        floor_sequence = int(
            floor.sequence
        )
        floor_root = str(
            floor.root_hash
        )
        if end_sequence <= floor_sequence:
            return self.archives.snapshot_segment(
                self.chain_id,
                start_exclusive_root,
                end_inclusive_root,
                max_items=max_items,
            )
        if start_sequence >= floor_sequence:
            return self.live_chain.snapshot_segment(
                start_exclusive_root,
                end_inclusive_root,
                max_items=max_items,
            )

        archived = tuple(
            self.archives.snapshot_segment(
                self.chain_id,
                start_exclusive_root,
                floor_root,
                max_items=(
                    floor_sequence
                    - start_sequence
                ),
            )
        )
        live = tuple(
            self.live_chain.snapshot_segment(
                floor_root,
                end_inclusive_root,
                max_items=(
                    end_sequence
                    - floor_sequence
                ),
            )
        )
        if len(archived) + len(live) != distance:
            raise DurableArchiveStoreError(
                "hot/cold historical segment length mismatch"
            )
        prefix = self._archive_prefix(floor)
        self._verify_splice(
            floor,
            prefix,
            live,
        )
        if archived:
            if (
                self._node_hash(archived[-1])
                != floor_root
                or self._node_sequence(
                    archived[-1]
                )
                != floor_sequence
            ):
                raise DurableArchiveStoreError(
                    "archived cross-floor segment does not terminate at hot floor"
                )
        return archived + live

    def verify_root(
        self,
        root_hash: str,
    ) -> bool:
        root_hash = _digest(
            "root_hash",
            root_hash,
        )
        try:
            floor = self._active_floor()
            if floor is None:
                try:
                    if self.live_chain.verify_root(
                        root_hash
                    ):
                        return True
                except Exception:
                    pass
                return self.archives.verify_root(
                    self.chain_id,
                    root_hash,
                )

            sequence = (
                self._sequence_for_root_live_or_archive(
                    root_hash
                )
            )
            if sequence <= int(floor.sequence):
                return self.archives.verify_root(
                    self.chain_id,
                    root_hash,
                )
            return bool(
                self.archives.verify_root(
                    self.chain_id,
                    str(floor.root_hash),
                )
                and self.live_chain.verify_root(
                    root_hash
                )
            )
        except Exception:
            return False

    def root_is_ancestor(
        self,
        root_hash: str,
    ) -> bool:
        root_hash = _digest(
            "root_hash",
            root_hash,
        )
        try:
            floor = self._active_floor()
            if floor is None:
                try:
                    if self.live_chain.root_is_ancestor(
                        root_hash
                    ):
                        return True
                except Exception:
                    pass
                return self.archives.root_is_archived(
                    self.chain_id,
                    root_hash,
                )

            sequence = (
                self._sequence_for_root_live_or_archive(
                    root_hash
                )
            )
            if sequence <= int(floor.sequence):
                if not self.archives.verify_root(
                    self.chain_id,
                    root_hash,
                ):
                    return False
                # A root below the floor is an ancestor iff the archive can
                # verify the bounded segment from that root through the exact
                # floor root.
                if root_hash == str(floor.root_hash):
                    return True
                try:
                    self.archives.snapshot_segment(
                        self.chain_id,
                        root_hash,
                        str(floor.root_hash),
                        max_items=(
                            int(floor.sequence)
                            - sequence
                        ),
                    )
                    return True
                except Exception:
                    return False

            return bool(
                self.live_chain.root_is_ancestor(
                    root_hash
                )
                and self.archives.verify_root(
                    self.chain_id,
                    str(floor.root_hash),
                )
            )
        except Exception:
            return False
