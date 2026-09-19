"""Durable multi-writer execution receipt chain.

This module implements the same append/snapshot/verify/root_hash surface as
ReceiptChain while storing immutable receipt nodes and the mutable chain head
in a versioned CAS backend. A secondary immutable receipt-id index lets
recovery code prove that a report's receipt identifiers are committed to the
authoritative chain.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Iterable

from skeleton.shells.ai.distributed_state import DistributedStateConflict
from skeleton.shells.ai.durable_hot_floor import (
    DurableHotFloorStore,
    HotFloorPosition,
)
from skeleton.shells.ai.store_protocol import VersionedStateBackend
from skeleton.shells.sequence_index import SequenceIndexBackfillBatch
from skeleton.shells.receipts import (
    ChainedReceipt,
    ExecutionReceipt,
    ReceiptChain,
)


GENESIS_HASH = ReceiptChain.GENESIS


def _sha256_hex(name: str, value: str) -> str:
    if len(value) != 64:
        raise ValueError(f"{name} must be SHA-256 hex")
    # Authority digests are opaque 64-character tokens at this boundary.
    return value.lower()


@dataclass(frozen=True)
class DistributedReceiptHead:
    sequence: int
    root_hash: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 0
        ):
            raise ValueError(
                "receipt sequence must be non-negative integer"
            )
        object.__setattr__(
            self,
            "root_hash",
            _sha256_hex("root_hash", self.root_hash),
        )
        if self.sequence == 0 and self.root_hash != GENESIS_HASH:
            raise ValueError(
                "empty receipt head must use genesis hash"
            )
        if self.sequence > 0 and self.root_hash == GENESIS_HASH:
            raise ValueError(
                "non-empty receipt head may not use genesis hash"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "root_hash": self.root_hash,
        }


@dataclass(frozen=True)
class DistributedReceiptSequenceIndex:
    sequence: int
    receipt_hash: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence <= 0
        ):
            raise ValueError("receipt sequence index must be positive")
        object.__setattr__(
            self,
            "receipt_hash",
            _sha256_hex("receipt_hash", self.receipt_hash),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "receipt_hash": self.receipt_hash,
        }


@dataclass(frozen=True)
class DistributedReceiptIndexHealth:
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
                raise ValueError(f"{name} must be non-negative integer")
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
                raise ValueError(f"{name} must be positive when present")

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
            "first_missing_sequence": self.first_missing_sequence,
            "first_corrupt_sequence": self.first_corrupt_sequence,
            "healthy": self.healthy,
        }


@dataclass(frozen=True)
class ReceiptIndexEntry:
    receipt_id: str
    receipt_hash: str
    receipt_fingerprint: str
    sequence: int

    def __post_init__(self) -> None:
        if not self.receipt_id or len(self.receipt_id) > 128:
            raise ValueError("invalid receipt_id")
        object.__setattr__(
            self,
            "receipt_hash",
            _sha256_hex(
                "receipt_hash",
                self.receipt_hash,
            ),
        )
        object.__setattr__(
            self,
            "receipt_fingerprint",
            _sha256_hex(
                "receipt_fingerprint",
                self.receipt_fingerprint,
            ),
        )
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence <= 0
        ):
            raise ValueError(
                "receipt index sequence must be positive integer"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "receipt_id": self.receipt_id,
            "receipt_hash": self.receipt_hash,
            "receipt_fingerprint": self.receipt_fingerprint,
            "sequence": self.sequence,
        }


@dataclass(frozen=True)
class ReceiptInclusion:
    entry: ReceiptIndexEntry
    node: ChainedReceipt
    committed: bool

    def __post_init__(self) -> None:
        if self.entry.receipt_hash != self.node.receipt_hash:
            raise ValueError(
                "receipt inclusion index/node hash mismatch"
            )
        if self.entry.sequence != self.node.sequence:
            raise ValueError(
                "receipt inclusion index/node sequence mismatch"
            )
        if (
            self.entry.receipt_id
            != self.node.receipt.receipt_id
        ):
            raise ValueError(
                "receipt inclusion receipt_id mismatch"
            )
        if (
            self.entry.receipt_fingerprint
            != self.node.receipt.fingerprint
        ):
            raise ValueError(
                "receipt inclusion fingerprint mismatch"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "entry": self.entry.to_dict(),
            "node": self.node.to_dict(),
            "committed": self.committed,
        }


class DistributedReceiptConflict(RuntimeError):
    pass


class DistributedReceiptCorruption(RuntimeError):
    pass


class DistributedReceiptChain:
    """CAS-backed receipt chain compatible with ReceiptChain callers."""

    def __init__(
        self,
        backend: VersionedStateBackend,
        *,
        namespace: str = "shell-receipts",
        max_receipts: int = 100_000,
        max_cas_retries: int = 32,
        hot_floor_store: DurableHotFloorStore | None = None,
        hot_floor_chain_id: str = "",
    ) -> None:
        if not namespace or len(namespace) > 128:
            raise ValueError("invalid receipt namespace")
        if (
            isinstance(max_receipts, bool)
            or not isinstance(max_receipts, int)
            or max_receipts <= 0
        ):
            raise ValueError(
                "max_receipts must be positive integer"
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
        self.namespace = namespace
        self.max_receipts = max_receipts
        self.max_cas_retries = max_cas_retries
        if (hot_floor_store is None) != (not hot_floor_chain_id):
            raise ValueError(
                "hot_floor_store and hot_floor_chain_id must be configured together"
            )
        if hot_floor_store is not None and not isinstance(
            hot_floor_store,
            DurableHotFloorStore,
        ):
            raise TypeError(
                "hot_floor_store must be DurableHotFloorStore"
            )
        if hot_floor_chain_id and len(hot_floor_chain_id) > 128:
            raise ValueError("hot_floor_chain_id too long")
        self.hot_floor_store = hot_floor_store
        self.hot_floor_chain_id = hot_floor_chain_id

    def hot_floor(self) -> HotFloorPosition:
        if self.hot_floor_store is None:
            return HotFloorPosition.genesis()
        return self.hot_floor_store.position(
            self.hot_floor_chain_id
        )

    def _hot_floor_active(
        self,
        floor: HotFloorPosition | None = None,
    ) -> bool:
        floor = floor or self.hot_floor()
        if floor.sequence == 0:
            return False
        return self.backend.get(
            self.namespace,
            self._node_key(floor.root_hash),
        ) is None

    def hot_length(self) -> int:
        head = self.head()
        floor = self.hot_floor()
        if self._hot_floor_active(floor):
            return max(0, head.sequence - floor.sequence)
        return head.sequence

    @staticmethod
    def _node_key(receipt_hash: str) -> str:
        return "node:" + _sha256_hex(
            "receipt_hash",
            receipt_hash,
        )

    @staticmethod
    def _sequence_key(sequence: int) -> str:
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence <= 0
        ):
            raise ValueError("sequence must be positive integer")
        return f"sequence:{sequence:020d}"

    @staticmethod
    def _index_key(receipt_id: str) -> str:
        if not receipt_id or len(receipt_id) > 128:
            raise ValueError("invalid receipt_id")
        return "receipt-id:" + hashlib.sha256(
            receipt_id.encode()
        ).hexdigest()

    def _sequence_index(
        self,
        sequence: int,
    ) -> DistributedReceiptSequenceIndex | None:
        record = self.backend.get(
            self.namespace,
            self._sequence_key(sequence),
        )
        if record is None:
            return None
        if not isinstance(
            record.value,
            DistributedReceiptSequenceIndex,
        ):
            raise DistributedReceiptCorruption(
                "receipt sequence index has invalid value type"
            )
        if record.value.sequence != sequence:
            raise DistributedReceiptCorruption(
                "receipt sequence index key/value mismatch"
            )
        return record.value

    def _put_sequence_index(
        self,
        item: ChainedReceipt,
    ) -> DistributedReceiptSequenceIndex:
        entry = DistributedReceiptSequenceIndex(
            item.sequence,
            item.receipt_hash,
        )
        key = self._sequence_key(item.sequence)
        existing = self.backend.get(
            self.namespace,
            key,
        )
        if existing is None:
            try:
                self.backend.put_if_absent(
                    self.namespace,
                    key,
                    entry,
                )
                return entry
            except DistributedStateConflict:
                existing = self.backend.get(
                    self.namespace,
                    key,
                )
                if existing is None:
                    raise
        if not isinstance(
            existing.value,
            DistributedReceiptSequenceIndex,
        ):
            raise DistributedReceiptCorruption(
                "receipt sequence index has invalid value type"
            )
        if existing.value != entry:
            raise DistributedReceiptCorruption(
                "receipt sequence already indexes a different node"
            )
        return existing.value

    def _repair_sequence_index(
        self,
        sequence: int,
    ) -> DistributedReceiptSequenceIndex:
        head = self.head()
        if sequence > head.sequence:
            raise IndexError(
                "receipt sequence is beyond committed head"
            )
        floor = self.hot_floor()
        if (
            self._hot_floor_active(floor)
            and sequence <= floor.sequence
        ):
            raise DistributedReceiptConflict(
                "receipt sequence was compacted from hot storage"
            )
        current_hash = head.root_hash
        current_sequence = head.sequence
        while current_sequence > sequence:
            item = self.get_node(current_hash)
            if item.sequence != current_sequence:
                raise DistributedReceiptCorruption(
                    "receipt sequence repair encountered non-contiguous chain"
                )
            current_hash = item.previous_hash
            current_sequence -= 1
        item = self.get_node(current_hash)
        if item.sequence != sequence:
            raise DistributedReceiptCorruption(
                "receipt sequence repair reached wrong sequence"
            )
        return self._put_sequence_index(item)

    def _head_revision(
        self,
    ) -> tuple[int, DistributedReceiptHead]:
        record = self.backend.get(
            self.namespace,
            "head",
        )
        if record is None:
            return 0, DistributedReceiptHead(
                0,
                GENESIS_HASH,
            )
        if not isinstance(
            record.value,
            DistributedReceiptHead,
        ):
            raise DistributedReceiptCorruption(
                "receipt head has invalid value type"
            )
        return record.revision, record.value

    def head(self) -> DistributedReceiptHead:
        return self._head_revision()[1]

    def _put_node(
        self,
        item: ChainedReceipt,
    ) -> None:
        key = self._node_key(item.receipt_hash)
        existing = self.backend.get(
            self.namespace,
            key,
        )
        if existing is None:
            try:
                self.backend.put_if_absent(
                    self.namespace,
                    key,
                    item,
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
            ChainedReceipt,
        ):
            raise DistributedReceiptCorruption(
                "receipt node key has invalid value type"
            )
        if existing.value != item:
            raise DistributedReceiptCorruption(
                "content-addressed receipt node collision"
            )

    def _put_index(
        self,
        item: ChainedReceipt,
    ) -> None:
        entry = ReceiptIndexEntry(
            item.receipt.receipt_id,
            item.receipt_hash,
            item.receipt.fingerprint,
            item.sequence,
        )
        key = self._index_key(
            item.receipt.receipt_id
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
                    entry,
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
            ReceiptIndexEntry,
        ):
            raise DistributedReceiptCorruption(
                "receipt index has invalid value type"
            )
        if existing.value != entry:
            raise DistributedReceiptConflict(
                "receipt_id already binds a different committed receipt"
            )

    def append(
        self,
        receipt: ExecutionReceipt,
    ) -> ChainedReceipt:
        if not isinstance(receipt, ExecutionReceipt):
            raise TypeError(
                "receipt must be ExecutionReceipt"
            )

        existing = self.find_by_receipt_id(
            receipt.receipt_id,
            verify_chain=False,
        )
        if existing is not None:
            if existing.node.receipt != receipt:
                raise DistributedReceiptConflict(
                    "receipt_id already binds different receipt content"
                )
            if existing.committed:
                return existing.node

        for _ in range(self.max_cas_retries):
            revision, head = self._head_revision()
            floor = self.hot_floor()
            live_receipts = max(
                0,
                head.sequence - (
                    floor.sequence
                    if self._hot_floor_active(floor)
                    else 0
                ),
            )
            if live_receipts >= self.max_receipts:
                raise RuntimeError(
                    "receipt chain capacity exhausted"
                )
            sequence = head.sequence + 1
            receipt_hash = ReceiptChain._hash(
                head.root_hash,
                sequence,
                receipt,
            )
            item = ChainedReceipt(
                sequence,
                head.root_hash,
                receipt_hash,
                receipt,
            )
            self._put_node(item)
            next_head = DistributedReceiptHead(
                sequence,
                receipt_hash,
            )
            try:
                self.backend.compare_and_swap(
                    self.namespace,
                    "head",
                    expected_revision=revision,
                    value=next_head,
                )
            except DistributedStateConflict:
                current_revision, current = (
                    self._head_revision()
                )
                if (
                    current.sequence == sequence
                    and current.root_hash == receipt_hash
                    and current_revision >= revision
                ):
                    self._put_sequence_index(item)
                    self._put_index(item)
                    return item
                if (
                    current_revision == revision
                    and current == head
                ):
                    raise
                continue
            self._put_sequence_index(item)
            self._put_index(item)
            return item

        raise DistributedReceiptConflict(
            "receipt head CAS retry budget exhausted"
        )

    def get_node(
        self,
        receipt_hash: str,
    ) -> ChainedReceipt:
        receipt_hash = _sha256_hex(
            "receipt_hash",
            receipt_hash,
        )
        record = self.backend.get(
            self.namespace,
            self._node_key(receipt_hash),
        )
        if record is None:
            raise DistributedReceiptCorruption(
                "committed receipt node is missing"
            )
        if not isinstance(
            record.value,
            ChainedReceipt,
        ):
            raise DistributedReceiptCorruption(
                "receipt node has invalid value type"
            )
        item = record.value
        expected = ReceiptChain._hash(
            item.previous_hash,
            item.sequence,
            item.receipt,
        )
        if expected != item.receipt_hash:
            raise DistributedReceiptCorruption(
                "receipt node digest mismatch"
            )
        if item.receipt_hash != receipt_hash:
            raise DistributedReceiptCorruption(
                "receipt node key/hash mismatch"
            )
        return item

    def get_by_sequence(
        self,
        sequence: int,
        *,
        repair_missing: bool = True,
    ) -> ChainedReceipt:
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence <= 0
        ):
            raise ValueError("sequence must be positive integer")
        head = self.head()
        if sequence > head.sequence:
            raise IndexError(
                "receipt sequence is beyond committed head"
            )
        floor = self.hot_floor()
        if (
            self._hot_floor_active(floor)
            and sequence <= floor.sequence
        ):
            raise DistributedReceiptConflict(
                "receipt sequence was compacted from hot storage"
            )
        entry = self._sequence_index(sequence)
        if entry is None:
            if not repair_missing:
                raise DistributedReceiptConflict(
                    "receipt sequence index is missing"
                )
            entry = self._repair_sequence_index(sequence)
        item = self.get_node(entry.receipt_hash)
        if item.sequence != sequence:
            raise DistributedReceiptCorruption(
                "receipt sequence index resolves wrong node sequence"
            )
        return item

    def root_for_sequence(
        self,
        sequence: int,
        *,
        repair_missing: bool = True,
    ) -> str:
        if sequence == 0:
            return GENESIS_HASH
        floor = self.hot_floor()
        if (
            self._hot_floor_active(floor)
            and sequence == floor.sequence
        ):
            return floor.root_hash
        if (
            self._hot_floor_active(floor)
            and sequence < floor.sequence
        ):
            raise DistributedReceiptConflict(
                "receipt root sequence was compacted from hot storage"
            )
        return self.get_by_sequence(
            sequence,
            repair_missing=repair_missing,
        ).receipt_hash

    def snapshot_range(
        self,
        start_sequence: int,
        end_sequence: int,
        *,
        max_items: int = 4096,
        repair_missing: bool = True,
    ) -> tuple[ChainedReceipt, ...]:
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
            raise ValueError("max_items must be positive integer")
        count = end_sequence - start_sequence + 1
        if count > max_items:
            raise DistributedReceiptConflict(
                "receipt range exceeds bounded verification window"
            )
        head = self.head()
        if end_sequence > head.sequence:
            raise IndexError(
                "receipt range extends beyond committed head"
            )
        start_root = self.root_for_sequence(
            start_sequence - 1,
            repair_missing=repair_missing,
        )
        end_root = self.root_for_sequence(
            end_sequence,
            repair_missing=repair_missing,
        )
        return self.snapshot_segment(
            start_root,
            end_root,
            max_items=max_items,
        )

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
            raise ValueError("max_items must be positive integer")
        head = self.head()
        if end_sequence is None:
            end_sequence = head.sequence
            end_root = head.root_hash
        if (
            isinstance(end_sequence, bool)
            or not isinstance(end_sequence, int)
            or end_sequence < 0
            or end_sequence > head.sequence
        ):
            raise ValueError(
                "end_sequence outside committed receipt range"
            )
        if end_sequence == 0:
            if end_root and end_root != GENESIS_HASH:
                raise DistributedReceiptConflict(
                    "zero-sequence backfill root must be genesis"
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
            if end_sequence != head.sequence:
                raise ValueError(
                    "historical receipt backfill requires explicit end_root"
                )
            end_root = head.root_hash
        end_root = _sha256_hex(
            "end_root",
            end_root,
        )
        terminal = self.get_node(end_root)
        if terminal.sequence != end_sequence:
            raise DistributedReceiptCorruption(
                "receipt backfill root/sequence mismatch"
            )

        requested_end_sequence = end_sequence
        requested_end_root = end_root
        current_sequence = end_sequence
        current_root = end_root
        indexed = 0
        already_indexed = 0
        processed = 0

        while current_sequence > 0 and processed < max_items:
            item = self.get_node(current_root)
            if item.sequence != current_sequence:
                raise DistributedReceiptCorruption(
                    "receipt backfill encountered non-contiguous sequence"
                )
            entry = self._sequence_index(
                current_sequence
            )
            if entry is None:
                self._put_sequence_index(item)
                indexed += 1
            elif entry.receipt_hash != item.receipt_hash:
                raise DistributedReceiptCorruption(
                    "receipt backfill found conflicting sequence index"
                )
            else:
                already_indexed += 1
            current_root = item.previous_hash
            current_sequence -= 1
            processed += 1

        covered_start = current_sequence + 1
        return SequenceIndexBackfillBatch(
            requested_end_sequence,
            requested_end_root,
            covered_start,
            requested_end_sequence,
            indexed,
            already_indexed,
            current_sequence,
            current_root,
            current_sequence == 0,
        )

    def inspect_sequence_indexes(
        self,
        *,
        max_items: int = 100_000,
    ) -> DistributedReceiptIndexHealth:
        if (
            isinstance(max_items, bool)
            or not isinstance(max_items, int)
            or max_items <= 0
        ):
            raise ValueError("max_items must be positive integer")
        items = self.snapshot()
        if len(items) > max_items:
            raise DistributedReceiptConflict(
                "receipt index inspection exceeds bounded window"
            )
        indexed = 0
        missing = 0
        corrupt = 0
        first_missing = None
        first_corrupt = None
        for item in items:
            try:
                entry = self._sequence_index(item.sequence)
            except DistributedReceiptCorruption:
                corrupt += 1
                if first_corrupt is None:
                    first_corrupt = item.sequence
                continue
            if entry is None:
                missing += 1
                if first_missing is None:
                    first_missing = item.sequence
                continue
            if entry.receipt_hash != item.receipt_hash:
                corrupt += 1
                if first_corrupt is None:
                    first_corrupt = item.sequence
                continue
            indexed += 1
        return DistributedReceiptIndexHealth(
            self.head().sequence,
            len(items),
            indexed,
            missing,
            corrupt,
            first_missing,
            first_corrupt,
        )

    def repair_sequence_indexes(
        self,
        *,
        max_items: int = 100_000,
    ) -> DistributedReceiptIndexHealth:
        if (
            isinstance(max_items, bool)
            or not isinstance(max_items, int)
            or max_items <= 0
        ):
            raise ValueError("max_items must be positive integer")
        items = self.snapshot()
        if len(items) > max_items:
            raise DistributedReceiptConflict(
                "receipt index repair exceeds bounded window"
            )
        for item in items:
            self._put_sequence_index(item)
        return self.inspect_sequence_indexes(
            max_items=max_items,
        )

    def snapshot(
        self,
    ) -> tuple[ChainedReceipt, ...]:
        head = self.head()
        if head.sequence == 0:
            return ()
        floor = self.hot_floor()
        floor_active = self._hot_floor_active(floor)
        current_hash = head.root_hash
        expected_sequence = head.sequence
        reverse: list[ChainedReceipt] = []
        seen: set[str] = set()

        while current_hash != GENESIS_HASH:
            if (
                floor_active
                and current_hash == floor.root_hash
            ):
                break
            if current_hash in seen:
                raise DistributedReceiptCorruption(
                    "receipt chain contains a cycle"
                )
            seen.add(current_hash)
            item = self.get_node(current_hash)
            if item.sequence != expected_sequence:
                raise DistributedReceiptCorruption(
                    "receipt chain sequence is not contiguous"
                )
            reverse.append(item)
            current_hash = item.previous_hash
            expected_sequence -= 1
            if expected_sequence < 0:
                raise DistributedReceiptCorruption(
                    "receipt chain sequence underflow"
                )

        expected_base = (
            floor.sequence
            if floor_active
            else 0
        )
        if expected_sequence != expected_base:
            raise DistributedReceiptCorruption(
                "receipt chain terminated before trusted hot floor"
            )
        items = tuple(reversed(reverse))
        if len(items) != (
            head.sequence - expected_base
        ):
            raise DistributedReceiptCorruption(
                "receipt snapshot length differs from live suffix"
            )
        return items

    def snapshot_at(
        self,
        root_hash: str,
    ) -> tuple[ChainedReceipt, ...]:
        """Return and verify the committed receipt prefix ending at root_hash."""
        root_hash = _sha256_hex(
            "root_hash",
            root_hash,
        )
        if root_hash == GENESIS_HASH:
            return ()
        floor = self.hot_floor()
        floor_active = self._hot_floor_active(floor)
        if floor_active and root_hash == floor.root_hash:
            return ()
        if floor_active:
            try:
                target_sequence = self.sequence_for_root(
                    root_hash
                )
            except (
                DistributedReceiptConflict,
                DistributedReceiptCorruption,
            ) as exc:
                raise DistributedReceiptCorruption(
                    "historical receipt root is below compacted hot floor"
                ) from exc
            if target_sequence < floor.sequence:
                raise DistributedReceiptCorruption(
                    "historical receipt root is below compacted hot floor"
                )
        root_item = self.get_node(root_hash)
        expected_sequence = root_item.sequence
        current_hash = root_hash
        reverse: list[ChainedReceipt] = []
        seen: set[str] = set()

        while current_hash != GENESIS_HASH:
            if (
                floor_active
                and current_hash == floor.root_hash
            ):
                break
            if current_hash in seen:
                raise DistributedReceiptCorruption(
                    "historical receipt chain contains a cycle"
                )
            seen.add(current_hash)
            item = self.get_node(current_hash)
            if item.sequence != expected_sequence:
                raise DistributedReceiptCorruption(
                    "historical receipt sequence is not contiguous"
                )
            reverse.append(item)
            current_hash = item.previous_hash
            expected_sequence -= 1
            if expected_sequence < 0:
                raise DistributedReceiptCorruption(
                    "historical receipt sequence underflow"
                )

        expected_base = (
            floor.sequence
            if floor_active
            else 0
        )
        if expected_sequence != expected_base:
            raise DistributedReceiptCorruption(
                "historical receipt chain did not reach trusted hot floor"
            )
        items = tuple(reversed(reverse))
        if not items or items[-1].receipt_hash != root_hash:
            raise DistributedReceiptCorruption(
                "historical receipt root mismatch"
            )
        return items

    def verify_root(
        self,
        root_hash: str,
    ) -> bool:
        try:
            items = self.snapshot_at(root_hash)
        except (
            DistributedReceiptCorruption,
            ValueError,
        ):
            return False
        floor = self.hot_floor()
        floor_active = self._hot_floor_active(floor)
        if floor_active and root_hash == floor.root_hash:
            return True
        previous = (
            floor.root_hash
            if floor_active
            else GENESIS_HASH
        )
        start_sequence = (
            floor.sequence + 1
            if floor_active
            else 1
        )
        for sequence, item in enumerate(
            items,
            start=start_sequence,
        ):
            if (
                item.sequence != sequence
                or item.previous_hash != previous
            ):
                return False
            expected = ReceiptChain._hash(
                previous,
                sequence,
                item.receipt,
            )
            if expected != item.receipt_hash:
                return False
            previous = item.receipt_hash
        return previous == root_hash

    def root_is_ancestor(
        self,
        root_hash: str,
    ) -> bool:
        root_hash = _sha256_hex(
            "root_hash",
            root_hash,
        )
        if root_hash == GENESIS_HASH:
            return True
        floor = self.hot_floor()
        if (
            self._hot_floor_active(floor)
            and root_hash == floor.root_hash
        ):
            return True
        if not self.verify_root(root_hash):
            return False
        try:
            current = self.snapshot()
        except DistributedReceiptCorruption:
            return False
        return any(
            item.receipt_hash == root_hash
            for item in current
        )

    def sequence_for_root(
        self,
        root_hash: str,
    ) -> int:
        root_hash = _sha256_hex(
            "root_hash",
            root_hash,
        )
        if root_hash == GENESIS_HASH:
            return 0
        floor = self.hot_floor()
        if (
            self._hot_floor_active(floor)
            and root_hash == floor.root_hash
        ):
            return floor.sequence
        return self.get_node(root_hash).sequence

    def snapshot_segment(
        self,
        start_exclusive_root: str,
        end_inclusive_root: str = "",
        *,
        max_items: int = 4096,
    ) -> tuple[ChainedReceipt, ...]:
        """Verify and return only the receipt segment after a trusted root."""
        if (
            isinstance(max_items, bool)
            or not isinstance(max_items, int)
            or max_items <= 0
        ):
            raise ValueError("max_items must be positive integer")
        start_exclusive_root = _sha256_hex(
            "start_exclusive_root",
            start_exclusive_root,
        )
        head = self.head()
        end_inclusive_root = _sha256_hex(
            "end_inclusive_root",
            end_inclusive_root or head.root_hash,
        )
        start_sequence = self.sequence_for_root(
            start_exclusive_root
        )
        end_sequence = self.sequence_for_root(
            end_inclusive_root
        )
        if end_sequence < start_sequence:
            raise DistributedReceiptCorruption(
                "receipt segment end precedes trusted start"
            )
        distance = end_sequence - start_sequence
        if distance > max_items:
            raise DistributedReceiptConflict(
                "receipt segment exceeds bounded verification window"
            )
        if distance == 0:
            if end_inclusive_root != start_exclusive_root:
                raise DistributedReceiptCorruption(
                    "equal receipt segment sequence has different roots"
                )
            return ()

        current_hash = end_inclusive_root
        expected_sequence = end_sequence
        reverse: list[ChainedReceipt] = []
        seen: set[str] = set()
        while current_hash != start_exclusive_root:
            if len(reverse) >= max_items:
                raise DistributedReceiptConflict(
                    "receipt segment exceeds bounded verification window"
                )
            if current_hash == GENESIS_HASH:
                raise DistributedReceiptCorruption(
                    "trusted receipt segment start is not an ancestor"
                )
            if current_hash in seen:
                raise DistributedReceiptCorruption(
                    "receipt segment contains a cycle"
                )
            seen.add(current_hash)
            item = self.get_node(current_hash)
            if item.sequence != expected_sequence:
                raise DistributedReceiptCorruption(
                    "receipt segment sequence is not contiguous"
                )
            reverse.append(item)
            current_hash = item.previous_hash
            expected_sequence -= 1

        if expected_sequence != start_sequence:
            raise DistributedReceiptCorruption(
                "receipt segment did not reach expected start sequence"
            )
        items = tuple(reversed(reverse))
        previous = start_exclusive_root
        sequence = start_sequence + 1
        for item in items:
            if (
                item.sequence != sequence
                or item.previous_hash != previous
            ):
                raise DistributedReceiptCorruption(
                    "receipt segment linkage mismatch"
                )
            expected = ReceiptChain._hash(
                previous,
                sequence,
                item.receipt,
            )
            if expected != item.receipt_hash:
                raise DistributedReceiptCorruption(
                    "receipt segment digest mismatch"
                )
            previous = item.receipt_hash
            sequence += 1
        if previous != end_inclusive_root:
            raise DistributedReceiptCorruption(
                "receipt segment end root mismatch"
            )
        return items

    def restore_segment(
        self,
        items: Iterable[ChainedReceipt],
        *,
        max_items: int = 4096,
    ) -> DistributedReceiptHead:
        """Restore an exact committed receipt segment onto this chain."""
        if (
            isinstance(max_items, bool)
            or not isinstance(max_items, int)
            or max_items <= 0
        ):
            raise ValueError("max_items must be positive integer")
        values = tuple(items)
        if len(values) > max_items:
            raise DistributedReceiptConflict(
                "receipt restore exceeds bounded segment size"
            )
        if not values:
            return self.head()

        previous_hash = values[0].previous_hash
        previous_sequence = values[0].sequence - 1
        if previous_sequence < 0:
            raise DistributedReceiptCorruption(
                "receipt restore begins before sequence one"
            )
        seen_receipt_ids: dict[str, str] = {}
        for offset, item in enumerate(values):
            if not isinstance(item, ChainedReceipt):
                raise TypeError(
                    "receipt restore items must be ChainedReceipt"
                )
            expected_sequence = previous_sequence + offset + 1
            if item.sequence != expected_sequence:
                raise DistributedReceiptCorruption(
                    "receipt restore sequence is not contiguous"
                )
            expected_previous = (
                previous_hash
                if offset == 0
                else values[offset - 1].receipt_hash
            )
            if item.previous_hash != expected_previous:
                raise DistributedReceiptCorruption(
                    "receipt restore linkage mismatch"
                )
            expected_hash = ReceiptChain._hash(
                item.previous_hash,
                item.sequence,
                item.receipt,
            )
            if expected_hash != item.receipt_hash:
                raise DistributedReceiptCorruption(
                    "receipt restore node digest mismatch"
                )
            if item.sequence > self.max_receipts:
                raise DistributedReceiptConflict(
                    "receipt restore exceeds chain capacity"
                )
            prior_hash = seen_receipt_ids.get(
                item.receipt.receipt_id
            )
            if (
                prior_hash is not None
                and prior_hash != item.receipt_hash
            ):
                raise DistributedReceiptConflict(
                    "receipt restore segment reuses receipt_id for different content"
                )
            seen_receipt_ids[
                item.receipt.receipt_id
            ] = item.receipt_hash
            existing = self.find_by_receipt_id(
                item.receipt.receipt_id,
                verify_chain=False,
            )
            if (
                existing is not None
                and existing.node.receipt_hash
                != item.receipt_hash
            ):
                raise DistributedReceiptConflict(
                    "receipt restore collides with existing receipt_id"
                )

        floor = self.hot_floor()
        if (
            self._hot_floor_active(floor)
            and values[0].sequence <= floor.sequence
        ):
            raise DistributedReceiptConflict(
                "receipt restore overlaps compacted hot floor"
            )

        for item in values:
            for _ in range(self.max_cas_retries):
                revision, head = self._head_revision()
                if head.sequence >= item.sequence:
                    try:
                        existing_root = self.root_for_sequence(
                            item.sequence,
                            repair_missing=True,
                        )
                    except (
                        DistributedReceiptConflict,
                        DistributedReceiptCorruption,
                        IndexError,
                    ) as exc:
                        raise DistributedReceiptConflict(
                            "receipt restore cannot verify existing target prefix"
                        ) from exc
                    if existing_root != item.receipt_hash:
                        raise DistributedReceiptConflict(
                            "receipt restore diverges from existing target prefix"
                        )
                    self._put_node(item)
                    self._put_sequence_index(item)
                    self._put_index(item)
                    break

                if head.sequence != item.sequence - 1:
                    raise DistributedReceiptConflict(
                        "receipt restore target has a sequence gap"
                    )
                if head.root_hash != item.previous_hash:
                    raise DistributedReceiptConflict(
                        "receipt restore target root diverges from segment"
                    )

                self._put_node(item)
                next_head = DistributedReceiptHead(
                    item.sequence,
                    item.receipt_hash,
                )
                try:
                    self.backend.compare_and_swap(
                        self.namespace,
                        "head",
                        expected_revision=revision,
                        value=next_head,
                    )
                except DistributedStateConflict:
                    continue
                self._put_sequence_index(item)
                self._put_index(item)
                break
            else:
                raise DistributedReceiptConflict(
                    "receipt restore CAS retry budget exhausted"
                )

        last = values[-1]
        current = self.head()
        if current.sequence < last.sequence:
            raise DistributedReceiptCorruption(
                "receipt restore ended before requested segment"
            )
        if self.root_for_sequence(last.sequence) != last.receipt_hash:
            raise DistributedReceiptConflict(
                "receipt restore final prefix differs from segment"
            )
        return current

    def verify_segment(
        self,
        start_exclusive_root: str,
        end_inclusive_root: str = "",
        *,
        max_items: int = 4096,
    ) -> bool:
        try:
            self.snapshot_segment(
                start_exclusive_root,
                end_inclusive_root,
                max_items=max_items,
            )
        except (
            DistributedReceiptConflict,
            DistributedReceiptCorruption,
            ValueError,
        ):
            return False
        return True

    def verify(self) -> bool:
        try:
            items = self.snapshot()
            head = self.head()
        except (
            DistributedReceiptCorruption,
            ValueError,
        ):
            return False

        floor = self.hot_floor()
        floor_active = self._hot_floor_active(floor)
        previous = (
            floor.root_hash
            if floor_active
            else GENESIS_HASH
        )
        start_sequence = (
            floor.sequence + 1
            if floor_active
            else 1
        )
        for sequence, item in enumerate(
            items,
            start=start_sequence,
        ):
            if (
                item.sequence != sequence
                or item.previous_hash != previous
            ):
                return False
            expected = ReceiptChain._hash(
                previous,
                sequence,
                item.receipt,
            )
            if expected != item.receipt_hash:
                return False
            previous = item.receipt_hash

        expected_base = (
            floor.sequence
            if floor_active
            else 0
        )
        expected_root = (
            previous
            if items
            else (
                floor.root_hash
                if floor_active
                else GENESIS_HASH
            )
        )
        return (
            head.sequence
            == expected_base + len(items)
            and head.root_hash == expected_root
        )

    def root_hash(self) -> str:
        return self.head().root_hash

    def length(self) -> int:
        return self.head().sequence

    def _is_committed(
        self,
        entry: ReceiptIndexEntry,
    ) -> bool:
        try:
            items = self.snapshot()
        except DistributedReceiptCorruption:
            return False
        floor = self.hot_floor()
        base_sequence = (
            floor.sequence
            if self._hot_floor_active(floor)
            else 0
        )
        if entry.sequence <= base_sequence:
            return False
        offset = entry.sequence - base_sequence - 1
        if offset < 0 or offset >= len(items):
            return False
        item = items[offset]
        return (
            item.receipt_hash == entry.receipt_hash
            and item.receipt.receipt_id
            == entry.receipt_id
        )

    def find_by_receipt_id(
        self,
        receipt_id: str,
        *,
        verify_chain: bool = True,
    ) -> ReceiptInclusion | None:
        key = self._index_key(receipt_id)
        record = self.backend.get(
            self.namespace,
            key,
        )
        if record is None:
            # A worker can crash after the head CAS and before the secondary
            # receipt-id index is written. Recover that narrow window by
            # scanning only the committed chain, then rebuild the immutable
            # index. This prevents a restart from appending the same receipt
            # a second time.
            matches = tuple(
                item
                for item in self.snapshot()
                if item.receipt.receipt_id
                == receipt_id
            )
            if not matches:
                return None
            if len(matches) != 1:
                raise DistributedReceiptCorruption(
                    "receipt id appears multiple times in committed chain"
                )
            self._put_index(matches[0])
            record = self.backend.get(
                self.namespace,
                key,
            )
            if record is None:
                raise DistributedReceiptCorruption(
                    "receipt index repair did not persist"
                )
        if not isinstance(
            record.value,
            ReceiptIndexEntry,
        ):
            raise DistributedReceiptCorruption(
                "receipt index has invalid value type"
            )
        entry = record.value
        floor = self.hot_floor()
        if (
            self._hot_floor_active(floor)
            and entry.sequence <= floor.sequence
        ):
            return None
        node = self.get_node(
            entry.receipt_hash,
        )
        committed = self._is_committed(entry)
        inclusion = ReceiptInclusion(
            entry,
            node,
            committed,
        )
        if verify_chain and not committed:
            raise DistributedReceiptCorruption(
                "receipt index references an uncommitted node"
            )
        return inclusion

    def require_receipt(
        self,
        receipt_id: str,
        *,
        fingerprint: str = "",
    ) -> ReceiptInclusion:
        inclusion = self.find_by_receipt_id(
            receipt_id,
            verify_chain=True,
        )
        if inclusion is None:
            raise DistributedReceiptConflict(
                "required receipt is missing"
            )
        if fingerprint:
            fingerprint = _sha256_hex(
                "fingerprint",
                fingerprint,
            )
            if (
                inclusion.entry.receipt_fingerprint
                != fingerprint
            ):
                raise DistributedReceiptConflict(
                    "receipt fingerprint differs from expected"
                )
        return inclusion

    def require_receipts(
        self,
        receipt_ids: Iterable[str],
    ) -> tuple[ReceiptInclusion, ...]:
        seen: set[str] = set()
        inclusions: list[ReceiptInclusion] = []
        for receipt_id in receipt_ids:
            if receipt_id in seen:
                raise DistributedReceiptConflict(
                    "duplicate receipt_id in inclusion request"
                )
            seen.add(receipt_id)
            inclusions.append(
                self.require_receipt(receipt_id)
            )
        return tuple(inclusions)

    def require_root(
        self,
        expected_root: str,
    ) -> DistributedReceiptHead:
        expected_root = _sha256_hex(
            "expected_root",
            expected_root,
        )
        head = self.head()
        if head.root_hash != expected_root:
            raise DistributedReceiptConflict(
                "receipt root differs from expected root"
            )
        if not self.verify():
            raise DistributedReceiptCorruption(
                "receipt chain failed integrity verification"
            )
        return head
