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
class DurableArchiveRootIndex:
    chain_id: str
    root_hash: str
    sequence: int
    archive_id: str
    archive_manifest_digest: str

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
        return DurableArchiveRootIndex(
            str(raw["chain_id"]),
            str(raw["root_hash"]),
            int(raw["sequence"]),
            str(raw["archive_id"]),
            str(raw["archive_manifest_digest"]),
        )

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
        if not self.checkpoints.verify():
            raise DurableArchiveStoreError("durable checkpoint registry is invalid")
        matches = tuple(
            item
            for item in self.checkpoints.for_chain(
                checkpoint.checkpoint.chain_id
            )
            if item.checkpoint.digest == checkpoint.checkpoint.digest
        )
        if len(matches) != 1:
            raise DurableArchiveStoreError(
                "archive checkpoint is not uniquely present in canonical registry"
            )
        if matches[0] != checkpoint:
            raise DurableArchiveStoreError(
                "archive checkpoint differs from canonical registry item"
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
        key = self._root_key(item.chain_id, item.root_hash)
        existing = self.backend.get(self.namespace, key)
        if existing is None:
            try:
                self.backend.put_if_absent(
                    self.namespace,
                    key,
                    item.to_dict(),
                )
                return True
            except DistributedStateConflict:
                existing = self.backend.get(
                    self.namespace,
                    key,
                )
                if existing is None:
                    raise
        if not isinstance(existing.value, dict):
            raise DurableArchiveStoreError(
                "archive root index must be mapping"
            )
        current = self._root_index(
            dict(existing.value)
        )
        if (
            current.chain_id != item.chain_id
            or current.root_hash != item.root_hash
            or current.sequence != item.sequence
        ):
            raise DurableArchiveStoreError(
                "archive root already binds incompatible historical position"
            )
        # The same committed historical root can legitimately be represented
        # by many later archives. Keep the first immutable index because it is
        # sufficient to reconstruct that prefix and avoids index churn.
        return False

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

        verification = self._builder.require(item, checkpoint, chain)
        if not verification.valid:
            raise DurableArchiveStoreError("archive failed live-chain verification")
        self._verify_manifest_signature(item)
        self._verify_checkpoint_authority(checkpoint)

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
        record_value = {
            "manifest": item.to_dict(),
            "checkpoint": checkpoint.to_dict(),
            "node_hashes": [node.node_hash for node in archived_nodes],
            "stored_at": float(now),
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
        stored = StoredDurableArchive(
            revision,
            manifest,
            checkpoint,
            tuple(str(item) for item in node_hashes_raw),
            float(raw["stored_at"]),
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
        if limit == 0:
            terminal = GENESIS_HASH
        else:
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
        return nodes

    def snapshot_at(
        self,
        chain_id: str,
        root_hash: str,
    ) -> tuple[object, ...]:
        root_hash = _digest("root_hash", root_hash)
        if root_hash == GENESIS_HASH:
            return ()
        index = self.root_index(chain_id, root_hash)
        if index is None:
            raise DurableArchiveStoreError("historical root is not archived")
        stored = self.get(index.archive_id)
        if stored is None:
            raise DurableArchiveStoreError(
                "archive root index references missing archive"
            )
        if stored.manifest.manifest.digest != index.archive_manifest_digest:
            raise DurableArchiveStoreError(
                "root index manifest digest mismatch"
            )
        if index.sequence > len(stored.node_hashes):
            raise DurableArchiveStoreError(
                "root index sequence exceeds archive"
            )
        nodes = self._stored_nodes(
            stored,
            through_sequence=index.sequence,
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
                "archived snapshot does not terminate at root"
            )
        return nodes

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
    """Read-through historical resolver over a live chain plus verified archive."""

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

    def head(self):
        return self.live_chain.head()

    def verify(self) -> bool:
        return bool(self.live_chain.verify())

    def snapshot(self):
        return self.live_chain.snapshot()

    def root_hash(self) -> str:
        if hasattr(self.live_chain, "root_hash"):
            return str(self.live_chain.root_hash())
        return str(self.live_chain.head().root_hash)

    def length(self) -> int:
        if hasattr(self.live_chain, "length"):
            return int(self.live_chain.length())
        return int(self.live_chain.head().sequence)

    def snapshot_at(
        self,
        root_hash: str,
    ):
        root_hash = _digest("root_hash", root_hash)
        try:
            return self.live_chain.snapshot_at(root_hash)
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

    def verify_root(
        self,
        root_hash: str,
    ) -> bool:
        try:
            if self.live_chain.verify_root(root_hash):
                return True
        except Exception:
            pass
        return self.archives.verify_root(
            self.chain_id,
            root_hash,
        )

    def root_is_ancestor(
        self,
        root_hash: str,
    ) -> bool:
        try:
            if self.live_chain.root_is_ancestor(root_hash):
                return True
        except Exception:
            pass
        return self.archives.root_is_archived(
            self.chain_id,
            root_hash,
        )
