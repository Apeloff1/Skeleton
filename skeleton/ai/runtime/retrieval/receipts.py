"""Bounded retrieval receipts for attributable, replay-safe feedback.

Receipts deliberately store hashes and result identifiers, never query text or
result content. They are durable enough to prevent duplicate feedback after a
restart while keeping the feedback authority bounded to an actual retrieval.
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

STATE_VERSION = 1


def query_digest(query: str) -> str:
    if not isinstance(query, str):
        raise TypeError("query must be a string")
    return hashlib.blake2b(query.encode("utf-8"), digest_size=16).hexdigest()


def receipt_id(sequence: int, digest: str, generation: int) -> str:
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise ValueError("sequence must be a positive integer")
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 0:
        raise ValueError("generation must be a non-negative integer")
    payload = f"{sequence}:{digest}:{generation}".encode("utf-8")
    return hashlib.blake2b(payload, digest_size=12).hexdigest()


def _string_tuple(name: str, values: Iterable[Any]) -> Tuple[str, ...]:
    output = tuple(str(value) for value in values)
    if any(not value for value in output):
        raise ValueError(f"{name} must contain non-empty strings")
    if len(set(output)) != len(output):
        raise ValueError(f"{name} must not contain duplicates")
    return output


@dataclass(frozen=True, slots=True)
class RetrievalReceipt:
    """Minimal immutable evidence binding feedback to a retrieval outcome."""

    receipt_id: str
    query_digest: str
    generation: int
    considered_planes: Tuple[str, ...]
    candidate_planes: Tuple[str, ...]
    failed_planes: Tuple[str, ...]
    fragment_planes: Tuple[Tuple[str, Tuple[str, ...]], ...]
    partial: bool
    created_ns: int
    source: str = "live"

    def __post_init__(self) -> None:
        if not self.receipt_id or not self.query_digest:
            raise ValueError("receipt_id and query_digest are required")
        if isinstance(self.generation, bool) or self.generation < 0:
            raise ValueError("generation must be non-negative")
        if isinstance(self.created_ns, bool) or self.created_ns < 0:
            raise ValueError("created_ns must be non-negative")
        if self.source not in {"live", "cache"}:
            raise ValueError("source must be live or cache")
        considered = set(self.considered_planes)
        if not set(self.candidate_planes).issubset(considered):
            raise ValueError("candidate planes must be a subset of considered planes")
        if not set(self.failed_planes).issubset(considered):
            raise ValueError("failed planes must be a subset of considered planes")
        seen = set()
        for fragment_id, planes in self.fragment_planes:
            if not fragment_id or fragment_id in seen:
                raise ValueError("fragment ids must be non-empty and unique")
            seen.add(fragment_id)
            if not planes or not set(planes).issubset(set(self.candidate_planes)):
                raise ValueError("fragment planes must reference candidate planes")

    def planes_for_fragment(self, fragment_id: str) -> Tuple[str, ...]:
        for candidate_id, planes in self.fragment_planes:
            if candidate_id == fragment_id:
                return planes
        return ()

    @property
    def fragment_ids(self) -> Tuple[str, ...]:
        return tuple(fragment_id for fragment_id, _ in self.fragment_planes)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "query_digest": self.query_digest,
            "generation": self.generation,
            "considered_planes": list(self.considered_planes),
            "candidate_planes": list(self.candidate_planes),
            "failed_planes": list(self.failed_planes),
            "fragment_planes": [
                {"fragment_id": fragment_id, "planes": list(planes)}
                for fragment_id, planes in self.fragment_planes
            ],
            "partial": self.partial,
            "created_ns": self.created_ns,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RetrievalReceipt":
        if not isinstance(payload, Mapping):
            raise ValueError("receipt payload must be a mapping")
        rows = payload.get("fragment_planes")
        if not isinstance(rows, list):
            raise ValueError("fragment_planes must be a list")
        fragment_planes = []
        for row in rows:
            if not isinstance(row, Mapping):
                raise ValueError("fragment plane row must be a mapping")
            fragment_id = row.get("fragment_id")
            planes = row.get("planes")
            if not isinstance(fragment_id, str) or not isinstance(planes, list):
                raise ValueError("fragment plane row is malformed")
            fragment_planes.append(
                (fragment_id, _string_tuple("fragment planes", planes))
            )
        generation = payload.get("generation")
        created_ns = payload.get("created_ns")
        partial = payload.get("partial")
        if isinstance(generation, bool) or not isinstance(generation, int):
            raise ValueError("generation must be an integer")
        if isinstance(created_ns, bool) or not isinstance(created_ns, int):
            raise ValueError("created_ns must be an integer")
        if not isinstance(partial, bool):
            raise ValueError("partial must be a boolean")
        return cls(
            receipt_id=str(payload.get("receipt_id") or ""),
            query_digest=str(payload.get("query_digest") or ""),
            generation=generation,
            considered_planes=_string_tuple(
                "considered_planes", payload.get("considered_planes") or ()
            ),
            candidate_planes=_string_tuple(
                "candidate_planes", payload.get("candidate_planes") or ()
            ),
            failed_planes=_string_tuple(
                "failed_planes", payload.get("failed_planes") or ()
            ),
            fragment_planes=tuple(fragment_planes),
            partial=partial,
            created_ns=created_ns,
            source=str(payload.get("source") or "live"),
        )


class ReceiptLedger:
    """Thread-safe bounded receipt ledger with exactly-once feedback markers."""

    def __init__(self, max_entries: int = 256) -> None:
        if isinstance(max_entries, bool) or not isinstance(max_entries, int):
            raise TypeError("max_entries must be an integer")
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self.max_entries = max_entries
        self._entries: OrderedDict[str, RetrievalReceipt] = OrderedDict()
        self._consumed: set[str] = set()
        self._lock = RLock()

    def record(self, receipt: RetrievalReceipt) -> None:
        if not isinstance(receipt, RetrievalReceipt):
            raise TypeError("receipt must be RetrievalReceipt")
        with self._lock:
            self._entries.pop(receipt.receipt_id, None)
            self._entries[receipt.receipt_id] = receipt
            while len(self._entries) > self.max_entries:
                evicted, _ = self._entries.popitem(last=False)
                self._consumed.discard(evicted)

    def get(self, receipt_id_value: str) -> Optional[RetrievalReceipt]:
        with self._lock:
            receipt = self._entries.get(receipt_id_value)
            if receipt is not None:
                self._entries.move_to_end(receipt_id_value)
            return receipt

    def require_available(self, receipt_id_value: str) -> RetrievalReceipt:
        with self._lock:
            receipt = self._entries.get(receipt_id_value)
            if receipt is None:
                raise KeyError("unknown or expired retrieval receipt")
            if receipt_id_value in self._consumed:
                raise ValueError("retrieval feedback receipt was already consumed")
            return receipt

    def mark_consumed(self, receipt_id_value: str) -> None:
        with self._lock:
            if receipt_id_value not in self._entries:
                raise KeyError("unknown or expired retrieval receipt")
            self._consumed.add(receipt_id_value)

    def consumed(self, receipt_id_value: str) -> bool:
        with self._lock:
            return receipt_id_value in self._consumed

    def recent(self, limit: int = 20) -> Tuple[RetrievalReceipt, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            raise ValueError("limit must be a non-negative integer")
        with self._lock:
            if limit == 0:
                return ()
            return tuple(list(self._entries.values())[-limit:])

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "version": STATE_VERSION,
                "max_entries": self.max_entries,
                "receipts": [receipt.to_dict() for receipt in self._entries.values()],
                "consumed": sorted(self._consumed),
            }

    @classmethod
    def from_snapshot(cls, payload: Mapping[str, Any]) -> "ReceiptLedger":
        if not isinstance(payload, Mapping):
            raise ValueError("receipt ledger state must be a mapping")
        if payload.get("version") != STATE_VERSION:
            raise ValueError("unsupported receipt ledger state version")
        max_entries = payload.get("max_entries")
        if isinstance(max_entries, bool) or not isinstance(max_entries, int):
            raise ValueError("max_entries must be an integer")
        receipts = payload.get("receipts")
        consumed = payload.get("consumed")
        if not isinstance(receipts, list) or not isinstance(consumed, list):
            raise ValueError("receipt ledger state is malformed")
        ledger = cls(max_entries=max_entries)
        for row in receipts:
            ledger.record(RetrievalReceipt.from_dict(row))
        consumed_set = set(consumed)
        if any(not isinstance(item, str) for item in consumed_set):
            raise ValueError("consumed receipt ids must be strings")
        if not consumed_set.issubset(set(ledger._entries)):
            raise ValueError("consumed receipt id has no retained receipt")
        ledger._consumed = consumed_set
        return ledger
