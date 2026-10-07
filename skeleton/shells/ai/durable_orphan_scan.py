"""Bounded discovery and classification of unreachable durable chain nodes.

CAS-backed append paths intentionally write immutable candidate nodes before
attempting to advance the authoritative head.  A losing CAS writer therefore
can leave an unreachable, content-addressed node behind.  Those records are
harmless to integrity but can accumulate indefinitely under sustained
multi-writer contention.

This module discovers such records without granting deletion authority.  It
requires an enumerable backend capability and classifies every hot-node record
into one of five buckets:

* reachable -- part of the current committed hot chain;
* compacted_retained -- at or below an active hot-floor boundary;
* orphan_candidate -- structurally valid, unreachable, unindexed candidate;
* index_conflict -- unreachable node still referenced by a sequence index;
* corrupt -- malformed, future-sequence, head/root, or otherwise inconsistent.

Only orphan_candidate records may ever be considered for garbage collection.
Deletion is deliberately implemented by a separate maintenance-gated operator.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import time
from typing import Callable, Iterable

from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
    DistributedJournalSequenceIndex,
)
from skeleton.shells.ai.store_protocol import (
    RecordListingBackend,
)
from skeleton.shells.distributed_receipts import (
    DistributedReceiptChain,
    DistributedReceiptSequenceIndex,
)


GENESIS_HASH = "0" * 64


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
        raise ValueError(f"{name} must be 64-character digest")
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


class DurableOrphanNodeKind(str, Enum):
    JOURNAL_EVENT = "journal_event"
    RECEIPT_NODE = "receipt_node"


class DurableOrphanRecordState(str, Enum):
    REACHABLE = "reachable"
    COMPACTED_RETAINED = "compacted_retained"
    ORPHAN_CANDIDATE = "orphan_candidate"
    INDEX_CONFLICT = "index_conflict"
    CORRUPT = "corrupt"


@dataclass(frozen=True)
class DurableOrphanScanPolicy:
    max_records: int = 100_000
    max_candidates: int = 10_000
    fail_on_candidate_overflow: bool = True
    include_reachable: bool = False
    include_compacted_retained: bool = True

    def __post_init__(self) -> None:
        for name in (
            "max_records",
            "max_candidates",
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
            "fail_on_candidate_overflow",
            "include_reachable",
            "include_compacted_retained",
        ):
            if not isinstance(
                getattr(self, name),
                bool,
            ):
                raise ValueError(
                    f"{name} must be bool"
                )

    def to_dict(self) -> dict[str, object]:
        return {
            "max_records": self.max_records,
            "max_candidates": self.max_candidates,
            "fail_on_candidate_overflow": (
                self.fail_on_candidate_overflow
            ),
            "include_reachable": self.include_reachable,
            "include_compacted_retained": (
                self.include_compacted_retained
            ),
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class DurableOrphanNodeRecord:
    chain_id: str
    node_kind: DurableOrphanNodeKind
    state: DurableOrphanRecordState
    backend_namespace: str
    backend_key: str
    backend_revision: int
    sequence: int
    node_hash: str
    previous_hash: str
    sequence_index_hash: str
    safe_to_delete: bool
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        object.__setattr__(
            self,
            "node_kind",
            DurableOrphanNodeKind(
                self.node_kind
            ),
        )
        object.__setattr__(
            self,
            "state",
            DurableOrphanRecordState(
                self.state
            ),
        )
        _identity(
            "backend_namespace",
            self.backend_namespace,
            maximum=128,
        )
        _identity(
            "backend_key",
            self.backend_key,
            maximum=512,
        )
        if (
            isinstance(self.backend_revision, bool)
            or not isinstance(self.backend_revision, int)
            or self.backend_revision <= 0
        ):
            raise ValueError(
                "backend_revision must be positive integer"
            )
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence <= 0
        ):
            raise ValueError(
                "orphan node sequence must be positive integer"
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
            "previous_hash",
            _digest(
                "previous_hash",
                self.previous_hash,
            ),
        )
        object.__setattr__(
            self,
            "sequence_index_hash",
            _digest(
                "sequence_index_hash",
                self.sequence_index_hash,
                optional=True,
            ),
        )
        if not isinstance(
            self.safe_to_delete,
            bool,
        ):
            raise ValueError(
                "safe_to_delete must be bool"
            )
        object.__setattr__(
            self,
            "reasons",
            tuple(self.reasons),
        )
        if any(
            not isinstance(item, str)
            or not item
            or len(item) > 2048
            for item in self.reasons
        ):
            raise ValueError(
                "invalid orphan node reason"
            )
        if (
            self.safe_to_delete
            and self.state
            is not DurableOrphanRecordState.ORPHAN_CANDIDATE
        ):
            raise ValueError(
                "only orphan candidates may be delete-safe"
            )

    @property
    def identity_digest(self) -> str:
        raw = json.dumps(
            {
                "chain_id": self.chain_id,
                "node_kind": self.node_kind.value,
                "backend_namespace": self.backend_namespace,
                "backend_key": self.backend_key,
                "backend_revision": self.backend_revision,
                "sequence": self.sequence,
                "node_hash": self.node_hash,
                "previous_hash": self.previous_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "chain_id": self.chain_id,
            "node_kind": self.node_kind.value,
            "state": self.state.value,
            "backend_namespace": self.backend_namespace,
            "backend_key": self.backend_key,
            "backend_revision": self.backend_revision,
            "sequence": self.sequence,
            "node_hash": self.node_hash,
            "previous_hash": self.previous_hash,
            "sequence_index_hash": self.sequence_index_hash,
            "safe_to_delete": self.safe_to_delete,
            "reasons": list(self.reasons),
            "identity_digest": self.identity_digest,
        }


@dataclass(frozen=True)
class DurableOrphanScanReport:
    chain_id: str
    node_kind: DurableOrphanNodeKind
    policy_digest: str
    head_sequence: int
    head_root: str
    floor_sequence: int
    floor_root: str
    floor_active: bool
    backend_records_inspected: int
    node_records_inspected: int
    records: tuple[DurableOrphanNodeRecord, ...]
    truncated: bool
    scanned_at: float

    def __post_init__(self) -> None:
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        object.__setattr__(
            self,
            "node_kind",
            DurableOrphanNodeKind(
                self.node_kind
            ),
        )
        object.__setattr__(
            self,
            "policy_digest",
            _digest(
                "policy_digest",
                self.policy_digest,
            ),
        )
        for name in (
            "head_sequence",
            "floor_sequence",
            "backend_records_inspected",
            "node_records_inspected",
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
        object.__setattr__(
            self,
            "head_root",
            _digest(
                "head_root",
                self.head_root,
            ),
        )
        object.__setattr__(
            self,
            "floor_root",
            _digest(
                "floor_root",
                self.floor_root,
            ),
        )
        if not isinstance(
            self.floor_active,
            bool,
        ):
            raise ValueError(
                "floor_active must be bool"
            )
        if not isinstance(
            self.truncated,
            bool,
        ):
            raise ValueError(
                "truncated must be bool"
            )
        object.__setattr__(
            self,
            "records",
            tuple(self.records),
        )
        if any(
            item.chain_id != self.chain_id
            or item.node_kind is not self.node_kind
            for item in self.records
        ):
            raise ValueError(
                "orphan report record binding mismatch"
            )
        identities = tuple(
            item.identity_digest
            for item in self.records
        )
        if len(identities) != len(
            set(identities)
        ):
            raise ValueError(
                "duplicate orphan report record"
            )
        object.__setattr__(
            self,
            "scanned_at",
            _timestamp(
                "scanned_at",
                self.scanned_at,
            ),
        )

    @property
    def reachable(self) -> int:
        return sum(
            item.state
            is DurableOrphanRecordState.REACHABLE
            for item in self.records
        )

    @property
    def compacted_retained(self) -> int:
        return sum(
            item.state
            is DurableOrphanRecordState.COMPACTED_RETAINED
            for item in self.records
        )

    @property
    def orphan_candidates(self) -> int:
        return sum(
            item.state
            is DurableOrphanRecordState.ORPHAN_CANDIDATE
            for item in self.records
        )

    @property
    def index_conflicts(self) -> int:
        return sum(
            item.state
            is DurableOrphanRecordState.INDEX_CONFLICT
            for item in self.records
        )

    @property
    def corrupt(self) -> int:
        return sum(
            item.state
            is DurableOrphanRecordState.CORRUPT
            for item in self.records
        )

    @property
    def safe_delete_candidates(
        self,
    ) -> tuple[DurableOrphanNodeRecord, ...]:
        return tuple(
            item
            for item in self.records
            if item.safe_to_delete
        )

    @property
    def requires_manual_review(self) -> bool:
        return (
            self.truncated
            or self.index_conflicts > 0
            or self.corrupt > 0
        )

    @property
    def healthy(self) -> bool:
        return not self.requires_manual_review

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(
                include_digest=False,
            ),
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
            "node_kind": self.node_kind.value,
            "policy_digest": self.policy_digest,
            "head_sequence": self.head_sequence,
            "head_root": self.head_root,
            "floor_sequence": self.floor_sequence,
            "floor_root": self.floor_root,
            "floor_active": self.floor_active,
            "backend_records_inspected": (
                self.backend_records_inspected
            ),
            "node_records_inspected": (
                self.node_records_inspected
            ),
            "records": [
                item.to_dict()
                for item in self.records
            ],
            "truncated": self.truncated,
            "scanned_at": self.scanned_at,
            "reachable": self.reachable,
            "compacted_retained": (
                self.compacted_retained
            ),
            "orphan_candidates": (
                self.orphan_candidates
            ),
            "index_conflicts": (
                self.index_conflicts
            ),
            "corrupt": self.corrupt,
            "safe_delete_candidates": len(
                self.safe_delete_candidates
            ),
            "requires_manual_review": (
                self.requires_manual_review
            ),
            "healthy": self.healthy,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


class DurableOrphanScanError(RuntimeError):
    pass


class DurableOrphanScanner:
    """Enumerate and classify unreachable immutable hot-store nodes."""

    def __init__(
        self,
        *,
        policy: DurableOrphanScanPolicy | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.policy = (
            policy or DurableOrphanScanPolicy()
        )
        if not isinstance(
            self.policy,
            DurableOrphanScanPolicy,
        ):
            raise TypeError(
                "policy must be DurableOrphanScanPolicy"
            )
        if not callable(clock):
            raise TypeError(
                "clock must be callable"
            )
        self._clock = clock

    @staticmethod
    def _backend(
        chain: object,
    ) -> RecordListingBackend:
        backend = getattr(
            chain,
            "backend",
            None,
        )
        if not isinstance(
            backend,
            RecordListingBackend,
        ):
            raise DurableOrphanScanError(
                "durable backend does not expose record listing capability"
            )
        return backend

    @staticmethod
    def _floor(
        chain: object,
    ) -> tuple[int, str, bool]:
        floor_method = getattr(
            chain,
            "hot_floor",
            None,
        )
        active_method = getattr(
            chain,
            "_hot_floor_active",
            None,
        )
        if not callable(floor_method):
            return 0, GENESIS_HASH, False
        floor = floor_method()
        sequence = int(
            getattr(floor, "sequence", 0)
        )
        root_hash = str(
            getattr(
                floor,
                "root_hash",
                GENESIS_HASH,
            )
        )
        active = bool(
            callable(active_method)
            and active_method(floor)
        )
        return (
            sequence,
            _digest(
                "floor_root",
                root_hash,
            ),
            active,
        )

    @staticmethod
    def _node_hash(
        item: object,
    ) -> str:
        return str(
            getattr(
                item,
                "event_hash",
                getattr(
                    item,
                    "receipt_hash",
                    "",
                ),
            )
        )

    @staticmethod
    def _node_previous_hash(
        item: object,
    ) -> str:
        return str(
            getattr(
                item,
                "previous_hash",
                "",
            )
        )

    @staticmethod
    def _node_sequence(
        item: object,
    ) -> int:
        return int(
            getattr(
                item,
                "sequence",
                0,
            )
        )

    @staticmethod
    def _kind(
        chain: object,
    ) -> tuple[
        DurableOrphanNodeKind,
        str,
        type,
        type,
        str,
    ]:
        if isinstance(
            chain,
            DistributedAIDecisionJournal,
        ):
            from skeleton.shells.ai.journal import (
                AIDecisionEvent,
            )
            return (
                DurableOrphanNodeKind.JOURNAL_EVENT,
                "event:",
                AIDecisionEvent,
                DistributedJournalSequenceIndex,
                "event_hash",
            )
        if isinstance(
            chain,
            DistributedReceiptChain,
        ):
            from skeleton.shells.receipts import (
                ChainedReceipt,
            )
            return (
                DurableOrphanNodeKind.RECEIPT_NODE,
                "node:",
                ChainedReceipt,
                DistributedReceiptSequenceIndex,
                "receipt_hash",
            )
        raise TypeError(
            "chain must be DistributedAIDecisionJournal "
            "or DistributedReceiptChain"
        )

    @staticmethod
    def _sequence_index(
        chain: object,
        sequence: int,
        index_type: type,
        hash_attribute: str,
    ) -> str:
        key_method = getattr(
            chain,
            "_sequence_key",
            None,
        )
        if not callable(key_method):
            return ""
        record = chain.backend.get(
            chain.namespace,
            key_method(sequence),
        )
        if record is None:
            return ""
        if not isinstance(
            record.value,
            index_type,
        ):
            raise DurableOrphanScanError(
                "sequence index has invalid value type"
            )
        return _digest(
            "sequence_index_hash",
            str(
                getattr(
                    record.value,
                    hash_attribute,
                )
            ),
        )

    @staticmethod
    def _reachable(
        chain: object,
    ) -> set[str]:
        try:
            items = tuple(
                chain.snapshot()
            )
        except Exception as exc:
            raise DurableOrphanScanError(
                "unable to reconstruct committed hot chain"
            ) from exc
        return {
            DurableOrphanScanner._node_hash(
                item
            )
            for item in items
        }

    @staticmethod
    def _validate_node(
        chain: object,
        *,
        value: object,
        key: str,
        prefix: str,
        expected_type: type,
    ) -> tuple[
        int,
        str,
        str,
        tuple[str, ...],
    ]:
        reasons: list[str] = []
        if not isinstance(
            value,
            expected_type,
        ):
            return (
                1,
                "0" * 64,
                "0" * 64,
                (
                    "node record has unexpected value type",
                ),
            )
        sequence = DurableOrphanScanner._node_sequence(
            value
        )
        node_hash = DurableOrphanScanner._node_hash(
            value
        )
        previous_hash = (
            DurableOrphanScanner
            ._node_previous_hash(value)
        )
        if sequence <= 0:
            reasons.append(
                "node sequence is not positive"
            )
            sequence = 1
        try:
            node_hash = _digest(
                "node_hash",
                node_hash,
            )
        except ValueError:
            reasons.append(
                "node hash is not digest-shaped"
            )
            node_hash = "0" * 64
        try:
            previous_hash = _digest(
                "previous_hash",
                previous_hash,
            )
        except ValueError:
            reasons.append(
                "previous hash is not digest-shaped"
            )
            previous_hash = "0" * 64
        if key != prefix + node_hash:
            reasons.append(
                "backend key does not match node hash"
            )
        if not reasons:
            try:
                getter = (
                    chain.get_event
                    if isinstance(
                        chain,
                        DistributedAIDecisionJournal,
                    )
                    else chain.get_node
                )
                resolved = getter(
                    node_hash
                )
                if resolved != value:
                    reasons.append(
                        "node getter resolves different content"
                    )
            except Exception as exc:
                reasons.append(
                    "node integrity verification failed: "
                    + type(exc).__name__
                )
        return (
            sequence,
            node_hash,
            previous_hash,
            tuple(reasons),
        )

    def scan(
        self,
        chain_id: str,
        chain: object,
    ) -> DurableOrphanScanReport:
        chain_id = _identity(
            "chain_id",
            chain_id,
            maximum=128,
        )
        (
            kind,
            prefix,
            expected_type,
            index_type,
            hash_attribute,
        ) = self._kind(chain)
        backend = self._backend(
            chain
        )
        namespace = _identity(
            "namespace",
            str(chain.namespace),
            maximum=128,
        )
        head = chain.head()
        head_sequence = int(
            getattr(head, "sequence")
        )
        head_root = _digest(
            "head_root",
            str(
                getattr(
                    head,
                    "root_hash",
                )
            ),
        )
        (
            floor_sequence,
            floor_root,
            floor_active,
        ) = self._floor(chain)
        reachable = self._reachable(
            chain
        )

        records = tuple(
            backend.records(namespace)
        )
        if len(records) > self.policy.max_records:
            inspected_records = records[
                : self.policy.max_records
            ]
            truncated = True
        else:
            inspected_records = records
            truncated = False

        classified: list[
            DurableOrphanNodeRecord
        ] = []
        candidate_count = 0
        node_records = 0

        for record in inspected_records:
            if not record.key.startswith(
                prefix
            ):
                continue
            node_records += 1
            (
                sequence,
                node_hash,
                previous_hash,
                validation_reasons,
            ) = self._validate_node(
                chain,
                value=record.value,
                key=record.key,
                prefix=prefix,
                expected_type=expected_type,
            )

            reasons = list(
                validation_reasons
            )
            state = (
                DurableOrphanRecordState.CORRUPT
                if reasons
                else DurableOrphanRecordState.REACHABLE
            )
            sequence_index_hash = ""

            if not reasons:
                try:
                    sequence_index_hash = (
                        self._sequence_index(
                            chain,
                            sequence,
                            index_type,
                            hash_attribute,
                        )
                    )
                except Exception as exc:
                    reasons.append(
                        "sequence index inspection failed: "
                        + type(exc).__name__
                    )
                    state = (
                        DurableOrphanRecordState.CORRUPT
                    )

            if not reasons:
                if node_hash in reachable:
                    state = (
                        DurableOrphanRecordState.REACHABLE
                    )
                elif node_hash == head_root:
                    state = (
                        DurableOrphanRecordState.CORRUPT
                    )
                    reasons.append(
                        "head root is not reachable from chain snapshot"
                    )
                elif sequence > head_sequence:
                    state = (
                        DurableOrphanRecordState.CORRUPT
                    )
                    reasons.append(
                        "node sequence is ahead of committed head"
                    )
                elif (
                    floor_active
                    and sequence <= floor_sequence
                ):
                    state = (
                        DurableOrphanRecordState.COMPACTED_RETAINED
                    )
                    reasons.append(
                        "node is retained below active hot floor"
                    )
                elif (
                    sequence_index_hash
                    and sequence_index_hash
                    == node_hash
                ):
                    state = (
                        DurableOrphanRecordState.INDEX_CONFLICT
                    )
                    reasons.append(
                        "unreachable node is referenced by sequence index"
                    )
                else:
                    ancestor = False
                    try:
                        ancestor = bool(
                            chain.root_is_ancestor(
                                node_hash
                            )
                        )
                    except Exception as exc:
                        state = (
                            DurableOrphanRecordState.CORRUPT
                        )
                        reasons.append(
                            "ancestor verification failed: "
                            + type(exc).__name__
                        )
                    if not reasons:
                        if ancestor:
                            state = (
                                DurableOrphanRecordState.CORRUPT
                            )
                            reasons.append(
                                "committed ancestor is absent from hot snapshot"
                            )
                        else:
                            state = (
                                DurableOrphanRecordState.ORPHAN_CANDIDATE
                            )
                            reasons.append(
                                "valid node is unreachable from committed head"
                            )

            safe_to_delete = (
                state
                is DurableOrphanRecordState.ORPHAN_CANDIDATE
                and sequence <= head_sequence
                and node_hash != head_root
                and not (
                    floor_active
                    and sequence <= floor_sequence
                )
                and sequence_index_hash
                != node_hash
            )
            item = DurableOrphanNodeRecord(
                chain_id,
                kind,
                state,
                namespace,
                record.key,
                record.revision,
                sequence,
                node_hash,
                previous_hash,
                sequence_index_hash,
                safe_to_delete,
                tuple(reasons),
            )

            include = (
                state
                is not DurableOrphanRecordState.REACHABLE
                or self.policy.include_reachable
            )
            if (
                state
                is DurableOrphanRecordState.COMPACTED_RETAINED
                and not self.policy.include_compacted_retained
            ):
                include = False
            if include:
                classified.append(
                    item
                )

            if safe_to_delete:
                candidate_count += 1
                if (
                    candidate_count
                    > self.policy.max_candidates
                ):
                    if (
                        self.policy.fail_on_candidate_overflow
                    ):
                        raise DurableOrphanScanError(
                            "orphan candidate count exceeds policy"
                        )
                    truncated = True
                    break

        classified.sort(
            key=lambda item: (
                item.sequence,
                item.node_hash,
                item.backend_key,
            )
        )
        scanned_at = _timestamp(
            "scan clock",
            self._clock(),
        )
        return DurableOrphanScanReport(
            chain_id,
            kind,
            self.policy.digest,
            head_sequence,
            head_root,
            floor_sequence,
            floor_root,
            floor_active,
            len(inspected_records),
            node_records,
            tuple(classified),
            truncated,
            scanned_at,
        )

    def require_clean(
        self,
        chain_id: str,
        chain: object,
        *,
        allow_orphans: bool = True,
    ) -> DurableOrphanScanReport:
        if not isinstance(
            allow_orphans,
            bool,
        ):
            raise ValueError(
                "allow_orphans must be bool"
            )
        report = self.scan(
            chain_id,
            chain,
        )
        if report.requires_manual_review:
            raise DurableOrphanScanError(
                "durable orphan scan requires manual review"
            )
        if (
            not allow_orphans
            and report.orphan_candidates
        ):
            raise DurableOrphanScanError(
                "durable orphan candidates are present"
            )
        return report
