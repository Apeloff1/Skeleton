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
from skeleton.shells.ai.store_protocol import VersionedStateBackend
from skeleton.shells.receipts import (
    ChainedReceipt,
    ExecutionReceipt,
    ReceiptChain,
)


GENESIS_HASH = ReceiptChain.GENESIS


def _sha256_hex(name: str, value: str) -> str:
    if len(value) != 64:
        raise ValueError(f"{name} must be SHA-256 hex")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{name} must be SHA-256 hex") from exc
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

    @staticmethod
    def _node_key(receipt_hash: str) -> str:
        return "node:" + _sha256_hex(
            "receipt_hash",
            receipt_hash,
        )

    @staticmethod
    def _index_key(receipt_id: str) -> str:
        if not receipt_id or len(receipt_id) > 128:
            raise ValueError("invalid receipt_id")
        return "receipt-id:" + hashlib.sha256(
            receipt_id.encode()
        ).hexdigest()

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
            if head.sequence >= self.max_receipts:
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
                    self._put_index(item)
                    return item
                if (
                    current_revision == revision
                    and current == head
                ):
                    raise
                continue
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

    def snapshot(
        self,
    ) -> tuple[ChainedReceipt, ...]:
        head = self.head()
        if head.sequence == 0:
            return ()
        current_hash = head.root_hash
        expected_sequence = head.sequence
        reverse: list[ChainedReceipt] = []
        seen: set[str] = set()

        while current_hash != GENESIS_HASH:
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

        if expected_sequence != 0:
            raise DistributedReceiptCorruption(
                "receipt chain terminated before genesis"
            )
        items = tuple(reversed(reverse))
        if len(items) != head.sequence:
            raise DistributedReceiptCorruption(
                "receipt snapshot length differs from head"
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
        root_item = self.get_node(root_hash)
        expected_sequence = root_item.sequence
        current_hash = root_hash
        reverse: list[ChainedReceipt] = []
        seen: set[str] = set()

        while current_hash != GENESIS_HASH:
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

        if expected_sequence != 0:
            raise DistributedReceiptCorruption(
                "historical receipt chain terminated before genesis"
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
        previous = GENESIS_HASH
        for sequence, item in enumerate(items, start=1):
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

    def verify(self) -> bool:
        try:
            items = self.snapshot()
            head = self.head()
        except (
            DistributedReceiptCorruption,
            ValueError,
        ):
            return False

        previous = GENESIS_HASH
        for sequence, item in enumerate(
            items,
            start=1,
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

        return (
            head.sequence == len(items)
            and head.root_hash == (
                previous if items else GENESIS_HASH
            )
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
        if entry.sequence > len(items):
            return False
        item = items[entry.sequence - 1]
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
