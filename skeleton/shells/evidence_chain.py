"""Content-addressed append-only evidence chains over a CAS state backend.

The chain stores immutable nodes by content hash and advances only a tiny head
record with compare-and-swap. A writer that loses the head CAS may leave an
unreachable immutable node, but it cannot corrupt the committed chain.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from types import MappingProxyType
from typing import Mapping, Protocol, runtime_checkable


GENESIS_HASH = "0" * 64


@runtime_checkable
class EvidenceStateBackend(Protocol):
    def get(self, namespace: str, key: str): ...

    def put_if_absent(self, namespace: str, key: str, value: object): ...

    def compare_and_swap(
        self,
        namespace: str,
        key: str,
        *,
        expected_revision: int,
        value: object,
    ): ...


@dataclass(frozen=True)
class EvidenceHead:
    sequence: int
    root_hash: str

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("evidence sequence may not be negative")
        if len(self.root_hash) != 64:
            raise ValueError("evidence root must be SHA-256 hex")
        if self.sequence == 0 and self.root_hash != GENESIS_HASH:
            raise ValueError("empty evidence head must use genesis hash")
        if self.sequence > 0 and self.root_hash == GENESIS_HASH:
            raise ValueError("non-empty evidence head may not use genesis hash")

    def to_dict(self) -> dict[str, object]:
        return {"sequence": self.sequence, "root_hash": self.root_hash}


@dataclass(frozen=True)
class EvidenceNode:
    sequence: int
    previous_hash: str
    node_hash: str
    kind: str
    payload: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.sequence <= 0:
            raise ValueError("evidence node sequence must be positive")
        if len(self.previous_hash) != 64 or len(self.node_hash) != 64:
            raise ValueError("evidence node hashes must be SHA-256 hex")
        if not self.kind or len(self.kind) > 128:
            raise ValueError("invalid evidence node kind")
        payload = dict(self.payload)
        if len(payload) > 256:
            raise ValueError("too many evidence payload fields")
        object.__setattr__(self, "payload", MappingProxyType(payload))

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "previous_hash": self.previous_hash,
            "node_hash": self.node_hash,
            "kind": self.kind,
            "payload": dict(self.payload),
        }


class EvidenceConflict(RuntimeError):
    pass


class EvidenceCorruption(RuntimeError):
    pass


class ContentAddressedEvidenceChain:
    """Append-only hash chain with CAS head and immutable content-addressed nodes."""

    def __init__(
        self,
        backend: EvidenceStateBackend,
        *,
        namespace: str,
        max_events: int = 100_000,
        max_cas_retries: int = 16,
    ) -> None:
        if not namespace or len(namespace) > 128:
            raise ValueError("invalid evidence namespace")
        if max_events <= 0:
            raise ValueError("max_events must be positive")
        if max_cas_retries <= 0:
            raise ValueError("max_cas_retries must be positive")
        self.backend = backend
        self.namespace = namespace
        self.max_events = max_events
        self.max_cas_retries = max_cas_retries

    @staticmethod
    def canonical_bytes(
        previous_hash: str,
        sequence: int,
        kind: str,
        payload: Mapping[str, object],
    ) -> bytes:
        return json.dumps(
            {
                "previous_hash": previous_hash,
                "sequence": sequence,
                "kind": kind,
                "payload": dict(payload),
            },
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()

    @classmethod
    def node_digest(
        cls,
        previous_hash: str,
        sequence: int,
        kind: str,
        payload: Mapping[str, object],
    ) -> str:
        return hashlib.sha256(
            cls.canonical_bytes(previous_hash, sequence, kind, payload)
        ).hexdigest()

    @staticmethod
    def _node_key(node_hash: str) -> str:
        return f"node:{node_hash}"

    def _read_head_record(self):
        return self.backend.get(self.namespace, "head")

    def head(self) -> EvidenceHead:
        record = self._read_head_record()
        if record is None:
            return EvidenceHead(0, GENESIS_HASH)
        if not isinstance(record.value, EvidenceHead):
            raise EvidenceCorruption("evidence head has invalid value type")
        return record.value

    def _head_revision(self) -> tuple[int, EvidenceHead]:
        record = self._read_head_record()
        if record is None:
            return 0, EvidenceHead(0, GENESIS_HASH)
        if not isinstance(record.value, EvidenceHead):
            raise EvidenceCorruption("evidence head has invalid value type")
        return record.revision, record.value

    def append(
        self,
        kind: str,
        payload: Mapping[str, object],
    ) -> EvidenceNode:
        if not kind or len(kind) > 128:
            raise ValueError("invalid evidence kind")
        frozen_payload = dict(payload)
        for _ in range(self.max_cas_retries):
            revision, head = self._head_revision()
            if head.sequence >= self.max_events:
                raise RuntimeError("evidence chain capacity exhausted")
            sequence = head.sequence + 1
            digest = self.node_digest(
                head.root_hash,
                sequence,
                kind,
                frozen_payload,
            )
            node = EvidenceNode(
                sequence,
                head.root_hash,
                digest,
                kind,
                frozen_payload,
            )
            node_key = self._node_key(digest)
            existing = self.backend.get(self.namespace, node_key)
            if existing is None:
                try:
                    self.backend.put_if_absent(
                        self.namespace,
                        node_key,
                        node,
                    )
                except Exception:
                    existing = self.backend.get(self.namespace, node_key)
                    if existing is None:
                        raise
            if existing is not None:
                if not isinstance(existing.value, EvidenceNode):
                    raise EvidenceCorruption("evidence node key has invalid value type")
                if existing.value != node:
                    raise EvidenceCorruption("content-addressed evidence node collision")
            new_head = EvidenceHead(sequence, digest)
            try:
                self.backend.compare_and_swap(
                    self.namespace,
                    "head",
                    expected_revision=revision,
                    value=new_head,
                )
                return node
            except Exception:
                current_revision, current = self._head_revision()
                if (
                    current.sequence == sequence
                    and current.root_hash == digest
                    and current_revision >= revision
                ):
                    return node
                continue
        raise EvidenceConflict("evidence head CAS retry budget exhausted")

    def get_node(self, node_hash: str) -> EvidenceNode:
        if len(node_hash) != 64:
            raise ValueError("node_hash must be SHA-256 hex")
        record = self.backend.get(
            self.namespace,
            self._node_key(node_hash),
        )
        if record is None or not isinstance(record.value, EvidenceNode):
            raise EvidenceCorruption("committed evidence node is missing")
        node = record.value
        expected = self.node_digest(
            node.previous_hash,
            node.sequence,
            node.kind,
            node.payload,
        )
        if expected != node.node_hash or node.node_hash != node_hash:
            raise EvidenceCorruption("evidence node digest mismatch")
        return node

    def snapshot(self) -> tuple[EvidenceNode, ...]:
        head = self.head()
        if head.sequence == 0:
            return ()
        current_hash = head.root_hash
        reverse = []
        expected_sequence = head.sequence
        seen = set()
        while current_hash != GENESIS_HASH:
            if current_hash in seen:
                raise EvidenceCorruption("evidence chain contains a cycle")
            seen.add(current_hash)
            node = self.get_node(current_hash)
            if node.sequence != expected_sequence:
                raise EvidenceCorruption("evidence sequence is not contiguous")
            reverse.append(node)
            current_hash = node.previous_hash
            expected_sequence -= 1
            if expected_sequence < 0:
                raise EvidenceCorruption("evidence chain underflow")
        if expected_sequence != 0:
            raise EvidenceCorruption("evidence chain terminated before genesis")
        items = tuple(reversed(reverse))
        if len(items) != head.sequence:
            raise EvidenceCorruption("evidence snapshot length differs from head")
        return items

    def verify(self) -> bool:
        try:
            items = self.snapshot()
        except (EvidenceCorruption, ValueError):
            return False
        previous = GENESIS_HASH
        for sequence, node in enumerate(items, start=1):
            if node.sequence != sequence or node.previous_hash != previous:
                return False
            expected = self.node_digest(
                previous,
                sequence,
                node.kind,
                node.payload,
            )
            if node.node_hash != expected:
                return False
            previous = node.node_hash
        head = self.head()
        return (
            head.sequence == len(items)
            and head.root_hash == (previous if items else GENESIS_HASH)
        )

    def root_hash(self) -> str:
        return self.head().root_hash

    def length(self) -> int:
        return self.head().sequence
