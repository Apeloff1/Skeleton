"""Signed append-only destruction ledger for durable evidence maintenance.

Destructive maintenance needs post-action evidence, not only pre-action
authorization.  This module records exactly what was deleted, why it was
authorized, what chain state existed before and after mutation, and whether
post-delete verification succeeded.

Records are immutable, content-addressed, HMAC-signed governance artifacts.
Each evidence chain has a CAS-serialized destruction head.  The head defines
committed history; immutable candidates left behind by a losing concurrent
writer are unreachable and therefore non-authoritative.

The operation index is a secondary idempotency index.  If a worker crashes
after committing the head but before writing that index, a later reader repairs
it by scanning only the committed destruction chain.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import time
from typing import Callable, Iterable

from skeleton.shells.ai.distributed_state import DistributedStateConflict
from skeleton.shells.ai.signed_artifact import (
    ArtifactSignatureError,
    ArtifactSigner,
    SignedArtifact,
)
from skeleton.shells.ai.store_protocol import VersionedStateBackend


GENESIS_DIGEST = "0" * 64
DESTRUCTION_ARTIFACT_TYPE = "shell-ai-durable-destruction-record"


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


class DurableDestructionKind(str, Enum):
    PRUNING = "pruning"
    ORPHAN_GC = "orphan_gc"


class DurableDestructionItemState(str, Enum):
    DELETED = "deleted"
    ALREADY_ABSENT = "already_absent"


@dataclass(frozen=True)
class DurableDestructionItem:
    item_kind: str
    backend_namespace: str
    backend_key: str
    node_hash: str
    state: DurableDestructionItemState
    expected_revision: int | None = None
    sequence: int | None = None
    receipt_id: str = ""
    archived: bool = False

    def __post_init__(self) -> None:
        _identity(
            "item_kind",
            self.item_kind,
            maximum=128,
        )
        _identity(
            "backend_namespace",
            self.backend_namespace,
            maximum=256,
        )
        _identity(
            "backend_key",
            self.backend_key,
            maximum=512,
        )
        object.__setattr__(
            self,
            "node_hash",
            _digest(
                "node_hash",
                self.node_hash,
            ),
        )
        object.__setattr__(
            self,
            "state",
            DurableDestructionItemState(
                self.state
            ),
        )
        for name in (
            "expected_revision",
            "sequence",
        ):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise ValueError(
                    f"{name} must be positive when supplied"
                )
        if len(self.receipt_id) > 128:
            raise ValueError(
                "receipt_id too long"
            )
        if not isinstance(self.archived, bool):
            raise ValueError(
                "archived must be bool"
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
            "item_kind": self.item_kind,
            "backend_namespace": (
                self.backend_namespace
            ),
            "backend_key": self.backend_key,
            "node_hash": self.node_hash,
            "state": self.state.value,
            "expected_revision": (
                self.expected_revision
            ),
            "sequence": self.sequence,
            "receipt_id": self.receipt_id,
            "archived": self.archived,
        }


@dataclass(frozen=True)
class DurableDestructionRecord:
    schema_version: int
    chain_id: str
    sequence: int
    previous_record_digest: str
    operation_kind: DurableDestructionKind
    operation_id: str
    authority_id: str
    authority_digest: str
    manifest_digest: str
    before_sequence: int
    before_root: str
    before_floor_sequence: int
    before_floor_root: str
    after_sequence: int
    after_root: str
    after_floor_sequence: int
    after_floor_root: str
    items: tuple[DurableDestructionItem, ...]
    archive_id: str = ""
    archive_manifest_digest: str = ""
    post_verify_digest: str = ""
    post_verified: bool = False
    completed_at: float = 0.0
    fencing_token: int = 0

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(
                "unsupported destruction record schema"
            )
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        object.__setattr__(
            self,
            "operation_kind",
            DurableDestructionKind(
                self.operation_kind
            ),
        )
        for name in (
            "operation_id",
            "authority_id",
        ):
            _identity(
                name,
                getattr(self, name),
                maximum=256,
            )
        for name in (
            "previous_record_digest",
            "authority_digest",
            "manifest_digest",
            "before_root",
            "before_floor_root",
            "after_root",
            "after_floor_root",
        ):
            object.__setattr__(
                self,
                name,
                _digest(
                    name,
                    getattr(self, name),
                ),
            )
        for name in (
            "archive_manifest_digest",
            "post_verify_digest",
        ):
            object.__setattr__(
                self,
                name,
                _digest(
                    name,
                    getattr(self, name),
                    optional=True,
                ),
            )
        for name in (
            "sequence",
            "before_sequence",
            "before_floor_sequence",
            "after_sequence",
            "after_floor_sequence",
            "fencing_token",
        ):
            value = getattr(self, name)
            minimum = (
                1
                if name in {
                    "sequence",
                    "fencing_token",
                }
                else 0
            )
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < minimum
            ):
                raise ValueError(
                    f"{name} outside supported range"
                )
        if (
            self.sequence == 1
            and self.previous_record_digest
            != GENESIS_DIGEST
        ):
            raise ValueError(
                "first destruction record must follow genesis"
            )
        if (
            self.sequence > 1
            and self.previous_record_digest
            == GENESIS_DIGEST
        ):
            raise ValueError(
                "non-first destruction record may not follow genesis"
            )
        if self.after_sequence < self.before_sequence:
            raise ValueError(
                "destruction may not move committed chain head backward"
            )
        if (
            self.after_sequence == self.before_sequence
            and self.after_root != self.before_root
        ):
            raise ValueError(
                "same committed head sequence may not bind different root"
            )
        if (
            self.after_floor_sequence
            < self.before_floor_sequence
        ):
            raise ValueError(
                "destruction may not move hot floor backward"
            )
        if (
            self.after_floor_sequence
            == self.before_floor_sequence
            and self.after_floor_root
            != self.before_floor_root
        ):
            raise ValueError(
                "same hot floor sequence may not bind different root"
            )
        items = tuple(self.items)
        object.__setattr__(
            self,
            "items",
            items,
        )
        if not items:
            raise ValueError(
                "destruction record requires at least one item"
            )
        if len(items) > 100_000:
            raise ValueError(
                "destruction record item bound exceeded"
            )
        keys = {
            (
                item.backend_namespace,
                item.backend_key,
            )
            for item in items
        }
        if len(keys) != len(items):
            raise ValueError(
                "destruction record contains duplicate backend keys"
            )
        if len(self.archive_id) > 256:
            raise ValueError(
                "archive_id too long"
            )
        if bool(self.archive_id) != bool(
            self.archive_manifest_digest
        ):
            raise ValueError(
                "archive id and manifest digest must be paired"
            )
        if (
            self.operation_kind
            is DurableDestructionKind.PRUNING
            and not self.archive_id
        ):
            raise ValueError(
                "pruning destruction requires archive binding"
            )
        if (
            self.operation_kind
            is DurableDestructionKind.PRUNING
            and not all(
                item.archived
                for item in items
            )
        ):
            raise ValueError(
                "pruning destruction items must be archived"
            )
        if not isinstance(
            self.post_verified,
            bool,
        ):
            raise ValueError(
                "post_verified must be bool"
            )
        if self.post_verified and not self.post_verify_digest:
            raise ValueError(
                "verified destruction requires post verification digest"
            )
        if not self.post_verified and self.post_verify_digest:
            raise ValueError(
                "unverified destruction may not carry verification digest"
            )
        object.__setattr__(
            self,
            "completed_at",
            _timestamp(
                "completed_at",
                self.completed_at,
            ),
        )

    @property
    def deleted_count(self) -> int:
        return sum(
            1
            for item in self.items
            if item.state
            is DurableDestructionItemState.DELETED
        )

    @property
    def already_absent_count(self) -> int:
        return sum(
            1
            for item in self.items
            if item.state
            is DurableDestructionItemState.ALREADY_ABSENT
        )

    @property
    def items_digest(self) -> str:
        raw = json.dumps(
            [
                item.to_dict()
                for item in self.items
            ],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def unsigned_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "chain_id": self.chain_id,
            "sequence": self.sequence,
            "previous_record_digest": (
                self.previous_record_digest
            ),
            "operation_kind": (
                self.operation_kind.value
            ),
            "operation_id": self.operation_id,
            "authority_id": self.authority_id,
            "authority_digest": (
                self.authority_digest
            ),
            "manifest_digest": (
                self.manifest_digest
            ),
            "before_sequence": self.before_sequence,
            "before_root": self.before_root,
            "before_floor_sequence": (
                self.before_floor_sequence
            ),
            "before_floor_root": (
                self.before_floor_root
            ),
            "after_sequence": self.after_sequence,
            "after_root": self.after_root,
            "after_floor_sequence": (
                self.after_floor_sequence
            ),
            "after_floor_root": (
                self.after_floor_root
            ),
            "items": [
                item.to_dict()
                for item in self.items
            ],
            "items_digest": self.items_digest,
            "archive_id": self.archive_id,
            "archive_manifest_digest": (
                self.archive_manifest_digest
            ),
            "post_verify_digest": (
                self.post_verify_digest
            ),
            "post_verified": self.post_verified,
            "completed_at": self.completed_at,
            "fencing_token": self.fencing_token,
            "authority": (
                "post-destruction-evidence"
            ),
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.unsigned_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    @property
    def operation_key(self) -> str:
        raw = json.dumps(
            {
                "chain_id": self.chain_id,
                "operation_kind": (
                    self.operation_kind.value
                ),
                "operation_id": (
                    self.operation_id
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(self) -> dict[str, object]:
        data = self.unsigned_dict()
        data["digest"] = self.digest
        data["operation_key"] = (
            self.operation_key
        )
        data["deleted_count"] = (
            self.deleted_count
        )
        data["already_absent_count"] = (
            self.already_absent_count
        )
        return data


@dataclass(frozen=True)
class SignedDurableDestructionRecord:
    record: DurableDestructionRecord
    signature: SignedArtifact

    def __post_init__(self) -> None:
        if not isinstance(
            self.record,
            DurableDestructionRecord,
        ):
            raise TypeError(
                "record must be DurableDestructionRecord"
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
        return self.record.digest

    @property
    def operation_key(self) -> str:
        return self.record.operation_key

    def to_dict(self) -> dict[str, object]:
        return {
            "record": self.record.to_dict(),
            "signature": (
                self.signature.to_dict()
            ),
        }


@dataclass(frozen=True)
class DurableDestructionHead:
    chain_id: str
    sequence: int
    record_id: str
    record_digest: str
    operation_key: str
    completed_at: float

    def __post_init__(self) -> None:
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence <= 0
        ):
            raise ValueError(
                "destruction head sequence must be positive"
            )
        for name in (
            "record_id",
            "record_digest",
            "operation_key",
        ):
            object.__setattr__(
                self,
                name,
                _digest(
                    name,
                    getattr(self, name),
                ),
            )
        object.__setattr__(
            self,
            "completed_at",
            _timestamp(
                "completed_at",
                self.completed_at,
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "chain_id": self.chain_id,
            "sequence": self.sequence,
            "record_id": self.record_id,
            "record_digest": (
                self.record_digest
            ),
            "operation_key": (
                self.operation_key
            ),
            "completed_at": self.completed_at,
        }


@dataclass(frozen=True)
class DurableDestructionOperationIndex:
    chain_id: str
    operation_key: str
    record_id: str
    record_digest: str
    sequence: int

    def __post_init__(self) -> None:
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        for name in (
            "operation_key",
            "record_id",
            "record_digest",
        ):
            object.__setattr__(
                self,
                name,
                _digest(
                    name,
                    getattr(self, name),
                ),
            )
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence <= 0
        ):
            raise ValueError(
                "destruction operation index sequence must be positive"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "chain_id": self.chain_id,
            "operation_key": (
                self.operation_key
            ),
            "record_id": self.record_id,
            "record_digest": (
                self.record_digest
            ),
            "sequence": self.sequence,
        }


@dataclass(frozen=True)
class DurableDestructionVerification:
    chain_id: str
    sequence: int
    records: int
    signatures_valid: bool
    linkage_valid: bool
    operation_indexes_valid: bool
    issues: tuple[str, ...]

    def __post_init__(self) -> None:
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        for name in (
            "sequence",
            "records",
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
        for name in (
            "signatures_valid",
            "linkage_valid",
            "operation_indexes_valid",
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
            "issues",
            tuple(self.issues),
        )

    @property
    def ok(self) -> bool:
        return (
            self.sequence == self.records
            and self.signatures_valid
            and self.linkage_valid
            and self.operation_indexes_valid
            and not self.issues
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "chain_id": self.chain_id,
            "sequence": self.sequence,
            "records": self.records,
            "signatures_valid": (
                self.signatures_valid
            ),
            "linkage_valid": (
                self.linkage_valid
            ),
            "operation_indexes_valid": (
                self.operation_indexes_valid
            ),
            "issues": list(self.issues),
            "ok": self.ok,
        }


class DurableDestructionError(RuntimeError):
    pass


class DurableDestructionConflict(DurableDestructionError):
    pass


class DurableDestructionCorruption(DurableDestructionError):
    pass


class DurableDestructionLedger:
    """CAS-serialized signed post-destruction evidence ledger."""

    def __init__(
        self,
        backend: VersionedStateBackend,
        signer: ArtifactSigner,
        *,
        namespace: str = "shell-ai-durable-destruction",
        max_records: int = 100_000,
        max_items_per_record: int = 100_000,
        max_cas_retries: int = 32,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not namespace or len(namespace) > 128:
            raise ValueError(
                "invalid destruction ledger namespace"
            )
        if not isinstance(
            signer,
            ArtifactSigner,
        ):
            raise TypeError(
                "signer must be ArtifactSigner"
            )
        for name, value, maximum in (
            (
                "max_records",
                max_records,
                10_000_000,
            ),
            (
                "max_items_per_record",
                max_items_per_record,
                1_000_000,
            ),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
                or value > maximum
            ):
                raise ValueError(
                    f"{name} outside supported range"
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
        self.backend = backend
        self.signer = signer
        self.namespace = namespace
        self.max_records = max_records
        self.max_items_per_record = (
            max_items_per_record
        )
        self.max_cas_retries = (
            max_cas_retries
        )
        self._clock = clock

    @staticmethod
    def _chain_hash(chain_id: str) -> str:
        _identity(
            "chain_id",
            chain_id,
            maximum=128,
        )
        return hashlib.sha256(
            chain_id.encode()
        ).hexdigest()

    @classmethod
    def _head_key(
        cls,
        chain_id: str,
    ) -> str:
        return "head:" + cls._chain_hash(
            chain_id
        )

    @staticmethod
    def _record_key(
        record_id: str,
    ) -> str:
        return "record:" + _digest(
            "record_id",
            record_id,
        )

    @staticmethod
    def _operation_index_key(
        operation_key: str,
    ) -> str:
        return "operation:" + _digest(
            "operation_key",
            operation_key,
        )

    @staticmethod
    def operation_key(
        chain_id: str,
        operation_kind: DurableDestructionKind,
        operation_id: str,
    ) -> str:
        _identity(
            "chain_id",
            chain_id,
            maximum=128,
        )
        operation_kind = (
            DurableDestructionKind(
                operation_kind
            )
        )
        _identity(
            "operation_id",
            operation_id,
            maximum=256,
        )
        raw = json.dumps(
            {
                "chain_id": chain_id,
                "operation_kind": (
                    operation_kind.value
                ),
                "operation_id": operation_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _signature(
        raw: dict[str, object],
    ) -> SignedArtifact:
        metadata = dict(
            raw.get("metadata", {})
        )
        return SignedArtifact(
            str(raw["artifact_type"]),
            str(raw["artifact_digest"]),
            str(raw["key_id"]),
            float(raw["issued_at"]),
            {
                str(key): str(value)
                for key, value
                in metadata.items()
            },
            str(raw["signature"]),
        )

    @staticmethod
    def _item(
        raw: dict[str, object],
    ) -> DurableDestructionItem:
        return DurableDestructionItem(
            str(raw["item_kind"]),
            str(raw["backend_namespace"]),
            str(raw["backend_key"]),
            str(raw["node_hash"]),
            DurableDestructionItemState(
                str(raw["state"])
            ),
            (
                None
                if raw.get(
                    "expected_revision"
                ) is None
                else int(
                    raw["expected_revision"]
                )
            ),
            (
                None
                if raw.get(
                    "sequence"
                ) is None
                else int(
                    raw["sequence"]
                )
            ),
            str(
                raw.get(
                    "receipt_id",
                    "",
                )
            ),
            bool(
                raw.get(
                    "archived",
                    False,
                )
            ),
        )

    @classmethod
    def _signed(
        cls,
        raw: dict[str, object],
    ) -> SignedDurableDestructionRecord:
        record_raw = dict(
            raw["record"]
        )
        items_raw = tuple(
            dict(item)
            for item in record_raw["items"]
        )
        record = DurableDestructionRecord(
            int(record_raw["schema_version"]),
            str(record_raw["chain_id"]),
            int(record_raw["sequence"]),
            str(
                record_raw[
                    "previous_record_digest"
                ]
            ),
            DurableDestructionKind(
                str(
                    record_raw[
                        "operation_kind"
                    ]
                )
            ),
            str(record_raw["operation_id"]),
            str(record_raw["authority_id"]),
            str(
                record_raw[
                    "authority_digest"
                ]
            ),
            str(
                record_raw[
                    "manifest_digest"
                ]
            ),
            int(record_raw["before_sequence"]),
            str(record_raw["before_root"]),
            int(
                record_raw[
                    "before_floor_sequence"
                ]
            ),
            str(
                record_raw[
                    "before_floor_root"
                ]
            ),
            int(record_raw["after_sequence"]),
            str(record_raw["after_root"]),
            int(
                record_raw[
                    "after_floor_sequence"
                ]
            ),
            str(
                record_raw[
                    "after_floor_root"
                ]
            ),
            tuple(
                cls._item(item)
                for item in items_raw
            ),
            str(
                record_raw.get(
                    "archive_id",
                    "",
                )
            ),
            str(
                record_raw.get(
                    "archive_manifest_digest",
                    "",
                )
            ),
            str(
                record_raw.get(
                    "post_verify_digest",
                    "",
                )
            ),
            bool(
                record_raw.get(
                    "post_verified",
                    False,
                )
            ),
            float(
                record_raw[
                    "completed_at"
                ]
            ),
            int(
                record_raw[
                    "fencing_token"
                ]
            ),
        )
        return SignedDurableDestructionRecord(
            record,
            cls._signature(
                dict(raw["signature"])
            ),
        )

    @staticmethod
    def _head(
        raw: dict[str, object],
    ) -> DurableDestructionHead:
        return DurableDestructionHead(
            str(raw["chain_id"]),
            int(raw["sequence"]),
            str(raw["record_id"]),
            str(raw["record_digest"]),
            str(raw["operation_key"]),
            float(raw["completed_at"]),
        )

    @staticmethod
    def _index(
        raw: dict[str, object],
    ) -> DurableDestructionOperationIndex:
        return DurableDestructionOperationIndex(
            str(raw["chain_id"]),
            str(raw["operation_key"]),
            str(raw["record_id"]),
            str(raw["record_digest"]),
            int(raw["sequence"]),
        )

    def _verify_signature(
        self,
        item: SignedDurableDestructionRecord,
    ) -> None:
        record = item.record
        signature = item.signature
        if (
            signature.artifact_type
            != DESTRUCTION_ARTIFACT_TYPE
        ):
            raise DurableDestructionCorruption(
                "destruction artifact type mismatch"
            )
        if (
            signature.artifact_digest
            != record.digest
        ):
            raise DurableDestructionCorruption(
                "destruction signature digest mismatch"
            )
        expected_metadata = {
            "chain_id": record.chain_id,
            "operation_kind": (
                record.operation_kind.value
            ),
            "operation_id": (
                record.operation_id
            ),
            "sequence": str(record.sequence),
            "authority": (
                "post-destruction-evidence"
            ),
        }
        if dict(signature.metadata) != expected_metadata:
            raise DurableDestructionCorruption(
                "destruction signature metadata mismatch"
            )
        try:
            self.signer.verify(
                signature
            )
        except ArtifactSignatureError as exc:
            raise DurableDestructionCorruption(
                "destruction signature verification failed"
            ) from exc

    def _head_record(
        self,
        chain_id: str,
    ):
        return self.backend.get(
            self.namespace,
            self._head_key(chain_id),
        )

    def head(
        self,
        chain_id: str,
    ) -> DurableDestructionHead | None:
        record = self._head_record(
            chain_id
        )
        if record is None:
            return None
        if not isinstance(
            record.value,
            dict,
        ):
            raise DurableDestructionCorruption(
                "destruction head must be mapping"
            )
        head = self._head(
            dict(record.value)
        )
        if head.chain_id != chain_id:
            raise DurableDestructionCorruption(
                "destruction head chain binding mismatch"
            )
        return head

    def get(
        self,
        record_id: str,
    ) -> SignedDurableDestructionRecord | None:
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
            dict,
        ):
            raise DurableDestructionCorruption(
                "destruction record must be mapping"
            )
        item = self._signed(
            dict(record.value)
        )
        if item.record_id != record_id:
            raise DurableDestructionCorruption(
                "destruction record key/digest mismatch"
            )
        self._verify_signature(
            item
        )
        return item

    def _put_record(
        self,
        item: SignedDurableDestructionRecord,
    ) -> bool:
        key = self._record_key(
            item.record_id
        )
        value = item.to_dict()
        existing = self.backend.get(
            self.namespace,
            key,
        )
        if existing is None:
            try:
                self.backend.put_if_absent(
                    self.namespace,
                    key,
                    value,
                )
                return True
            except DistributedStateConflict:
                existing = self.backend.get(
                    self.namespace,
                    key,
                )
                if existing is None:
                    raise
        if not isinstance(
            existing.value,
            dict,
        ):
            raise DurableDestructionCorruption(
                "destruction record must be mapping"
            )
        current = self._signed(
            dict(existing.value)
        )
        if current != item:
            raise DurableDestructionCorruption(
                "destruction digest collision"
            )
        return False

    def _put_operation_index(
        self,
        item: SignedDurableDestructionRecord,
    ) -> None:
        index = DurableDestructionOperationIndex(
            item.record.chain_id,
            item.operation_key,
            item.record_id,
            item.record.digest,
            item.record.sequence,
        )
        key = self._operation_index_key(
            item.operation_key
        )
        existing = self.backend.get(
            self.namespace,
            key,
        )
        if existing is None:
            try:
                self.backend.put_if_absent(
                    self.namespace,
                    key,
                    index.to_dict(),
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
            dict,
        ):
            raise DurableDestructionCorruption(
                "destruction operation index must be mapping"
            )
        current = self._index(
            dict(existing.value)
        )
        if current != index:
            raise DurableDestructionConflict(
                "operation already binds different destruction record"
            )

    def _committed_snapshot(
        self,
        chain_id: str,
    ) -> tuple[
        SignedDurableDestructionRecord,
        ...,
    ]:
        head = self.head(
            chain_id
        )
        if head is None:
            return ()
        current_digest = (
            head.record_digest
        )
        expected_sequence = (
            head.sequence
        )
        reverse: list[
            SignedDurableDestructionRecord
        ] = []
        seen: set[str] = set()
        while current_digest != GENESIS_DIGEST:
            if current_digest in seen:
                raise DurableDestructionCorruption(
                    "destruction ledger contains cycle"
                )
            seen.add(current_digest)
            item = self.get(
                current_digest
            )
            if item is None:
                raise DurableDestructionCorruption(
                    "committed destruction record is missing"
                )
            record = item.record
            if record.chain_id != chain_id:
                raise DurableDestructionCorruption(
                    "destruction record chain mismatch"
                )
            if (
                record.sequence
                != expected_sequence
            ):
                raise DurableDestructionCorruption(
                    "destruction sequence is not contiguous"
                )
            reverse.append(item)
            current_digest = (
                record.previous_record_digest
            )
            expected_sequence -= 1
            if expected_sequence < 0:
                raise DurableDestructionCorruption(
                    "destruction sequence underflow"
                )
        if expected_sequence != 0:
            raise DurableDestructionCorruption(
                "destruction ledger terminated before genesis"
            )
        items = tuple(
            reversed(reverse)
        )
        if (
            not items
            or items[-1].record.digest
            != head.record_digest
            or items[-1].record_id
            != head.record_id
        ):
            raise DurableDestructionCorruption(
                "destruction head does not match chain tail"
            )
        return items

    def snapshot(
        self,
        chain_id: str,
    ) -> tuple[
        SignedDurableDestructionRecord,
        ...,
    ]:
        return self._committed_snapshot(
            chain_id
        )

    def find_operation(
        self,
        chain_id: str,
        operation_kind: DurableDestructionKind,
        operation_id: str,
    ) -> SignedDurableDestructionRecord | None:
        operation_key = self.operation_key(
            chain_id,
            operation_kind,
            operation_id,
        )
        key = self._operation_index_key(
            operation_key
        )
        stored = self.backend.get(
            self.namespace,
            key,
        )
        if stored is None:
            # Repair the post-head-CAS/pre-index crash window from committed
            # history only. Unreachable candidate records are ignored.
            matches = tuple(
                item
                for item
                in self.snapshot(chain_id)
                if item.operation_key
                == operation_key
            )
            if not matches:
                return None
            if len(matches) != 1:
                raise DurableDestructionCorruption(
                    "operation appears multiple times in destruction ledger"
                )
            self._put_operation_index(
                matches[0]
            )
            stored = self.backend.get(
                self.namespace,
                key,
            )
            if stored is None:
                raise DurableDestructionCorruption(
                    "destruction operation index repair failed"
                )
        if not isinstance(
            stored.value,
            dict,
        ):
            raise DurableDestructionCorruption(
                "destruction operation index must be mapping"
            )
        index = self._index(
            dict(stored.value)
        )
        if (
            index.chain_id != chain_id
            or index.operation_key
            != operation_key
        ):
            raise DurableDestructionCorruption(
                "destruction operation index binding mismatch"
            )
        item = self.get(
            index.record_id
        )
        if item is None:
            raise DurableDestructionCorruption(
                "destruction operation index references missing record"
            )
        if (
            item.record.digest
            != index.record_digest
            or item.record.sequence
            != index.sequence
            or item.operation_key
            != operation_key
        ):
            raise DurableDestructionCorruption(
                "destruction operation index differs from record"
            )
        committed = {
            entry.record.digest
            for entry
            in self.snapshot(chain_id)
        }
        if item.record.digest not in committed:
            raise DurableDestructionCorruption(
                "destruction operation index references uncommitted record"
            )
        return item

    def append(
        self,
        *,
        chain_id: str,
        operation_kind: DurableDestructionKind,
        operation_id: str,
        authority_id: str,
        authority_digest: str,
        manifest_digest: str,
        before_sequence: int,
        before_root: str,
        before_floor_sequence: int,
        before_floor_root: str,
        after_sequence: int,
        after_root: str,
        after_floor_sequence: int,
        after_floor_root: str,
        items: Iterable[DurableDestructionItem],
        archive_id: str = "",
        archive_manifest_digest: str = "",
        post_verify_digest: str = "",
        post_verified: bool = False,
        fencing_token: int = 0,
        completed_at: float | None = None,
    ) -> SignedDurableDestructionRecord:
        operation_kind = (
            DurableDestructionKind(
                operation_kind
            )
        )
        existing = self.find_operation(
            chain_id,
            operation_kind,
            operation_id,
        )
        items_tuple = tuple(items)
        if len(items_tuple) > self.max_items_per_record:
            raise ValueError(
                "destruction item bound exceeded"
            )
        if existing is not None:
            # Reconstruct against the committed predecessor to prove a retry
            # carries exactly the same operation evidence.
            record = existing.record
            candidate = DurableDestructionRecord(
                1,
                chain_id,
                record.sequence,
                record.previous_record_digest,
                operation_kind,
                operation_id,
                authority_id,
                authority_digest,
                manifest_digest,
                before_sequence,
                before_root,
                before_floor_sequence,
                before_floor_root,
                after_sequence,
                after_root,
                after_floor_sequence,
                after_floor_root,
                items_tuple,
                archive_id,
                archive_manifest_digest,
                post_verify_digest,
                post_verified,
                record.completed_at,
                fencing_token,
            )
            if candidate.digest != record.digest:
                raise DurableDestructionConflict(
                    "destruction operation retry carries different evidence"
                )
            return existing

        if completed_at is None:
            completed_at = self._clock()
        completed_at = _timestamp(
            "completed_at",
            completed_at,
        )

        for _ in range(
            self.max_cas_retries
        ):
            head_record = self._head_record(
                chain_id
            )
            if head_record is None:
                head = None
                head_revision = 0
                sequence = 1
                previous_digest = (
                    GENESIS_DIGEST
                )
            else:
                if not isinstance(
                    head_record.value,
                    dict,
                ):
                    raise DurableDestructionCorruption(
                        "destruction head must be mapping"
                    )
                head = self._head(
                    dict(head_record.value)
                )
                if head.chain_id != chain_id:
                    raise DurableDestructionCorruption(
                        "destruction head chain mismatch"
                    )
                head_revision = (
                    head_record.revision
                )
                sequence = (
                    head.sequence + 1
                )
                previous_digest = (
                    head.record_digest
                )
            if sequence > self.max_records:
                raise RuntimeError(
                    "destruction ledger capacity exhausted"
                )
            record = DurableDestructionRecord(
                1,
                chain_id,
                sequence,
                previous_digest,
                operation_kind,
                operation_id,
                authority_id,
                authority_digest,
                manifest_digest,
                before_sequence,
                before_root,
                before_floor_sequence,
                before_floor_root,
                after_sequence,
                after_root,
                after_floor_sequence,
                after_floor_root,
                items_tuple,
                archive_id,
                archive_manifest_digest,
                post_verify_digest,
                post_verified,
                completed_at,
                fencing_token,
            )
            signature = self.signer.sign(
                DESTRUCTION_ARTIFACT_TYPE,
                record.digest,
                metadata={
                    "chain_id": chain_id,
                    "operation_kind": (
                        operation_kind.value
                    ),
                    "operation_id": (
                        operation_id
                    ),
                    "sequence": (
                        str(sequence)
                    ),
                    "authority": (
                        "post-destruction-evidence"
                    ),
                },
            )
            item = (
                SignedDurableDestructionRecord(
                    record,
                    signature,
                )
            )
            self._put_record(
                item
            )
            next_head = DurableDestructionHead(
                chain_id,
                sequence,
                item.record_id,
                record.digest,
                record.operation_key,
                completed_at,
            )
            try:
                self.backend.compare_and_swap(
                    self.namespace,
                    self._head_key(
                        chain_id
                    ),
                    expected_revision=(
                        head_revision
                    ),
                    value=next_head.to_dict(),
                )
            except DistributedStateConflict:
                winner = self.find_operation(
                    chain_id,
                    operation_kind,
                    operation_id,
                )
                if winner is not None:
                    if (
                        winner.record.digest
                        == record.digest
                    ):
                        return winner
                    raise DurableDestructionConflict(
                        "concurrent destruction operation differs"
                    )
                continue
            self._put_operation_index(
                item
            )
            return item

        raise DurableDestructionConflict(
            "destruction head CAS retry budget exhausted"
        )

    def verify(
        self,
        chain_id: str,
    ) -> DurableDestructionVerification:
        issues: list[str] = []
        signatures_valid = True
        linkage_valid = True
        indexes_valid = True
        try:
            items = self.snapshot(
                chain_id
            )
        except Exception as exc:
            return DurableDestructionVerification(
                chain_id,
                0,
                0,
                False,
                False,
                False,
                (
                    "destruction snapshot failed: "
                    f"{type(exc).__name__}",
                ),
            )
        previous = (
            GENESIS_DIGEST
        )
        for sequence, item in enumerate(
            items,
            start=1,
        ):
            record = item.record
            if (
                record.sequence != sequence
                or record.previous_record_digest
                != previous
            ):
                linkage_valid = False
                issues.append(
                    f"sequence {sequence} linkage mismatch"
                )
            try:
                self._verify_signature(
                    item
                )
            except DurableDestructionCorruption as exc:
                signatures_valid = False
                issues.append(
                    f"sequence {sequence} signature: {exc}"
                )
            try:
                indexed = self.find_operation(
                    chain_id,
                    record.operation_kind,
                    record.operation_id,
                )
                if (
                    indexed is None
                    or indexed.record.digest
                    != record.digest
                ):
                    indexes_valid = False
                    issues.append(
                        f"sequence {sequence} operation index mismatch"
                    )
            except DurableDestructionError as exc:
                indexes_valid = False
                issues.append(
                    f"sequence {sequence} operation index: {exc}"
                )
            previous = record.digest
        head = self.head(
            chain_id
        )
        head_sequence = (
            0
            if head is None
            else head.sequence
        )
        if head_sequence != len(items):
            linkage_valid = False
            issues.append(
                "destruction head sequence differs from snapshot length"
            )
        return DurableDestructionVerification(
            chain_id,
            head_sequence,
            len(items),
            signatures_valid,
            linkage_valid,
            indexes_valid,
            tuple(issues),
        )

    def require_verified(
        self,
        chain_id: str,
    ) -> DurableDestructionVerification:
        report = self.verify(
            chain_id
        )
        if not report.ok:
            detail = (
                report.issues[0]
                if report.issues
                else "destruction ledger verification failed"
            )
            raise DurableDestructionCorruption(
                detail
            )
        return report
