"""Merkle-anchored event log — tamper-evident bus replay.

The kernel's event bus is the system of record; if an attacker (or a
buggy subscriber) rewrites history, every downstream decision is
poisoned. This module appends every event to a hash-chained log and
periodically anchors batches into a Merkle tree, giving the kernel:

- **Tamper evidence** — each entry carries the hash of its predecessor;
  altering any byte invalidates every subsequent link.
- **Inclusion proofs** — :meth:`MerkleAnchor.prove` emits a compact
  audit path proving an event sits under a given root, verifiable in
  O(log n) without the full log.
- **Replay integrity** — :meth:`verify_chain` re-walks the whole log;
  cheap enough to run on every startup.

Stdlib ``hashlib``/``json`` only. Hashes are SHA-256; serialisation is
canonical JSON so digests are reproducible across processes.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .errors import EventBusError


class LogIntegrityError(EventBusError):
    code = "KRN.LOG_INTEGRITY"
    http_status = 409


GENESIS = "0" * 64


def _canonical(data: Dict[str, Any]) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class LogEntry:
    """One hash-linked event record."""

    index: int
    event_id: str
    topic: str
    payload: Dict[str, Any]
    timestamp: float
    prev_hash: str
    entry_hash: str

    @classmethod
    def create(cls, index: int, event_id: str, topic: str,
               payload: Dict[str, Any], prev_hash: str) -> "LogEntry":
        ts = time.time()
        body = {
            "index": index, "event_id": event_id, "topic": topic,
            "payload": payload, "timestamp": ts, "prev_hash": prev_hash,
        }
        return cls(index, event_id, topic, payload, ts, prev_hash, _sha256(_canonical(body)))

    def verify_link(self, prev_hash: str) -> bool:
        body = {
            "index": self.index, "event_id": self.event_id,
            "topic": self.topic, "payload": self.payload,
            "timestamp": self.timestamp, "prev_hash": prev_hash,
        }
        return (
            self.prev_hash == prev_hash
            and self.entry_hash == _sha256(_canonical(body))
        )


def _merkle_root(leaves: Sequence[str]) -> str:
    if not leaves:
        return GENESIS
    level = [_sha256(bytes.fromhex(h)) for h in leaves]
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [
            _sha256(bytes.fromhex(level[i]) + bytes.fromhex(level[i + 1]))
            for i in range(0, len(level), 2)
        ]
    return level[0]


@dataclass(frozen=True)
class InclusionProof:
    leaf_hash: str
    leaf_index: int
    path: Tuple[Tuple[str, str], ...]  # (sibling_hash, side) — side in {"L","R"}
    root: str

    def verify(self) -> bool:
        node = self.leaf_hash
        for sibling, side in self.path:
            if side == "L":
                node = _sha256(bytes.fromhex(sibling) + bytes.fromhex(node))
            else:
                node = _sha256(bytes.fromhex(node) + bytes.fromhex(sibling))
        return node == self.root


@dataclass
class MerkleAnchor:
    """A sealed batch of log entries with its computed root."""

    anchor_id: str
    first_index: int
    last_index: int
    root: str
    leaf_hashes: List[str] = field(default_factory=list)

    @classmethod
    def seal(cls, anchor_id: str, entries: Sequence[LogEntry]) -> "MerkleAnchor":
        leaves = [e.entry_hash for e in entries]
        return cls(
            anchor_id=anchor_id,
            first_index=entries[0].index,
            last_index=entries[-1].index,
            root=_merkle_root(leaves),
            leaf_hashes=leaves,
        )

    def prove(self, entry_index: int) -> InclusionProof:
        pos = entry_index - self.first_index
        if not 0 <= pos < len(self.leaf_hashes):
            raise LogIntegrityError(
                "entry not under this anchor",
                context={"entry_index": entry_index, "anchor": self.anchor_id},
            )
        level = [_sha256(bytes.fromhex(h)) for h in self.leaf_hashes]
        idx, path = pos, []
        while len(level) > 1:
            if len(level) % 2:
                level.append(level[-1])
            sibling = idx + 1 if idx % 2 == 0 else idx - 1
            path.append((level[sibling], "R" if idx % 2 == 0 else "L"))
            idx //= 2
            level = [
                _sha256(bytes.fromhex(level[i]) + bytes.fromhex(level[i + 1]))
                for i in range(0, len(level), 2)
            ]
        return InclusionProof(level[0], pos, tuple(path), self.root) \
            if False else InclusionProof(
                leaf_hash=level[0], leaf_index=pos, path=tuple(path), root=self.root
            )


class MerkleEventLog:
    """Append-only, hash-chained log with periodic Merkle anchoring."""

    def __init__(self, anchor_every: int = 64) -> None:
        if anchor_every < 1:
            raise LogIntegrityError("anchor_every must be >= 1")
        self.anchor_every = anchor_every
        self._entries: List[LogEntry] = []
        self._anchors: List[MerkleAnchor] = []
        self._anchor_seq = 0

    @property
    def head_hash(self) -> str:
        return self._entries[-1].entry_hash if self._entries else GENESIS

    def append(self, event_id: str, topic: str, payload: Dict[str, Any]) -> LogEntry:
        entry = LogEntry.create(
            index=len(self._entries),
            event_id=event_id,
            topic=topic,
            payload=payload,
            prev_hash=self.head_hash,
        )
        self._entries.append(entry)
        pending = len(self._entries) - (self._anchors[-1].last_index + 1 if self._anchors else 0)
        if pending >= self.anchor_every:
            self._seal_pending()
        return entry

    def _seal_pending(self) -> MerkleAnchor:
        start = self._anchors[-1].last_index + 1 if self._anchors else 0
        batch = self._entries[start:]
        self._anchor_seq += 1
        anchor = MerkleAnchor.seal(f"anchor-{self._anchor_seq:06d}", batch)
        self._anchors.append(anchor)
        return anchor

    def seal(self) -> MerkleAnchor:
        """Force-seal any pending entries (e.g. at shutdown)."""
        return self._seal_pending()

    @property
    def anchors(self) -> Tuple[MerkleAnchor, ...]:
        return tuple(self._anchors)

    def entry(self, index: int) -> LogEntry:
        return self._entries[index]

    def __len__(self) -> int:
        return len(self._entries)

    def verify_chain(self) -> bool:
        """Re-walk the entire chain; True iff every link and digest holds."""
        prev = GENESIS
        for entry in self._entries:
            if not entry.verify_link(prev):
                return False
            prev = entry.entry_hash
        return True

    def prove(self, entry_index: int) -> InclusionProof:
        for anchor in self._anchors:
            if anchor.first_index <= entry_index <= anchor.last_index:
                return anchor.prove(entry_index)
        raise LogIntegrityError(
            "entry is not yet under any anchor — call seal() first",
            context={"entry_index": entry_index},
        )
