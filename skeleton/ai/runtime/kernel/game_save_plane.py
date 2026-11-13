"""Game Frontier save / restore / replay plane (GF-B).

Extends :mod:`skeleton.kernel.checkpoint` — it does not replace it. All
saves go through one :class:`CheckpointStore` (the canonical sealed,
monotonic, bounded checkpoint authority); this module adds:

- :class:`ChunkReceiptStore` — content-addressed per-chunk receipts
  (SHA-256 of canonical JSON), deduplicated, with stable cursor-based
  pagination (GF-P0-148).
- :class:`GameSavePlane` — sectioned world saves (world axis, weather,
  variants, structures, motion, calibration ...), schema migrations
  applied on restore, backups = retained checkpoints, rollback to any
  retained sequence (GF-P0-14 / GF-P0-36 / GF-P0-99 persistence half).
- :class:`ReplayJournal` — append-only frame history keyed by frame
  number with idempotent append (same frame + same digest is a no-op,
  different digest is a conflict), a bounded AI-context cursor, and
  deterministic replay from a restored checkpoint (GF-P0-117).

Pure in-memory ports; storage adapters can back the same surface.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from .checkpoint import Checkpoint, CheckpointError, CheckpointStore

SAVE_SCHEMA_VERSION = 1


class SavePlaneError(CheckpointError):
    """Save/restore/replay contract violation."""


class ReplayConflictError(SavePlaneError):
    """Two different payloads claimed the same frame."""


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def content_digest(obj: Any) -> str:
    return hashlib.sha256(_canon(obj).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Paged chunk receipts (GF-P0-148)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ChunkReceipt:
    chunk_id: str
    sequence: int
    digest: str
    body: Dict[str, Any]

    def verify(self) -> None:
        if content_digest(self.body) != self.digest:
            raise SavePlaneError("chunk receipt digest mismatch",
                                 context={"chunk_id": self.chunk_id})


@dataclass(frozen=True)
class ReceiptPage:
    items: Tuple[ChunkReceipt, ...]
    next_cursor: Optional[int]
    total: int


class ChunkReceiptStore:
    """Content-addressed, append-only receipts with cursor pagination."""

    def __init__(self, *, max_page_size: int = 500) -> None:
        if max_page_size < 1:
            raise SavePlaneError("max_page_size must be >= 1")
        self.max_page_size = max_page_size
        self._log: List[ChunkReceipt] = []
        self._by_digest: Dict[str, ChunkReceipt] = {}

    def put(self, chunk_id: str, body: Mapping[str, Any]) -> ChunkReceipt:
        body = dict(body)
        digest = content_digest({"chunk_id": chunk_id, "body": body})
        existing = self._by_digest.get(digest)
        if existing is not None:
            return existing  # idempotent
        receipt = ChunkReceipt(chunk_id=chunk_id, sequence=len(self._log),
                               digest=content_digest(body), body=body)
        self._log.append(receipt)
        self._by_digest[digest] = receipt
        return receipt

    def page(self, *, cursor: int = 0, limit: int = 100,
             chunk_id: Optional[str] = None) -> ReceiptPage:
        if cursor < 0 or limit < 1:
            raise SavePlaneError("invalid page request",
                                 context={"cursor": cursor, "limit": limit})
        limit = min(limit, self.max_page_size)
        out: List[ChunkReceipt] = []
        idx = cursor
        while idx < len(self._log) and len(out) < limit:
            r = self._log[idx]
            if chunk_id is None or r.chunk_id == chunk_id:
                r.verify()
                out.append(r)
            idx += 1
        total = (len(self._log) if chunk_id is None
                 else sum(1 for r in self._log if r.chunk_id == chunk_id))
        nxt = idx if idx < len(self._log) else None
        return ReceiptPage(items=tuple(out), next_cursor=nxt, total=total)

    def root(self) -> str:
        """Order-sensitive root over all receipt digests (manifest seal)."""
        return content_digest([r.digest for r in self._log])

    def to_state(self) -> Dict[str, Any]:
        return {"receipts": [{"chunk_id": r.chunk_id, "body": r.body}
                             for r in self._log]}

    @classmethod
    def from_state(cls, state: Mapping[str, Any], **kw: Any) -> "ChunkReceiptStore":
        store = cls(**kw)
        for item in state.get("receipts", ()):
            store.put(item["chunk_id"], item["body"])
        return store


# --------------------------------------------------------------------------
# Sectioned saves + migrations + rollback (GF-P0-14 / 36 / 99)
# --------------------------------------------------------------------------

Migration = Callable[[Dict[str, Any]], Dict[str, Any]]


class GameSavePlane:
    COMPONENT_PREFIX = "game-save:"

    def __init__(self, *, store: Optional[CheckpointStore] = None,
                 schema_version: int = SAVE_SCHEMA_VERSION) -> None:
        self.store = store or CheckpointStore(retain=8)
        self.schema_version = schema_version
        self._migrations: Dict[int, Migration] = {}

    def register_migration(self, from_version: int, fn: Migration) -> None:
        if from_version in self._migrations:
            raise SavePlaneError("migration already registered",
                                 context={"from": from_version})
        self._migrations[from_version] = fn

    def _component(self, slot: str) -> str:
        return self.COMPONENT_PREFIX + slot

    def save(self, slot: str, sequence: int,
             sections: Mapping[str, Mapping[str, Any]],
             *, receipts: Optional[ChunkReceiptStore] = None) -> Checkpoint:
        state: Dict[str, Any] = {
            "schema_version": self.schema_version,
            "sections": {k: dict(v) for k, v in sections.items()},
        }
        if receipts is not None:
            state["receipts"] = receipts.to_state()
            state["receipt_root"] = receipts.root()
        return self.store.save(self._component(slot), sequence, state)

    def _migrate(self, state: Dict[str, Any]) -> Dict[str, Any]:
        version = int(state.get("schema_version", 0))
        if version > self.schema_version:
            raise SavePlaneError("save is newer than runtime",
                                 context={"save": version,
                                          "runtime": self.schema_version})
        while version < self.schema_version:
            fn = self._migrations.get(version)
            if fn is None:
                raise SavePlaneError("missing migration",
                                     context={"from": version})
            state = fn(dict(state))
            version += 1
            state["schema_version"] = version
        return state

    def restore(self, slot: str, *, sequence: Optional[int] = None
                ) -> Tuple[Dict[str, Any], Optional[ChunkReceiptStore]]:
        """Restore latest verified save (or exact ``sequence`` = rollback)."""
        comp = self._component(slot)
        ckpt: Optional[Checkpoint]
        if sequence is None:
            ckpt = self.store.restore(comp)
        else:
            ckpt = next((c for c in self.store.history(comp)
                         if c.sequence == sequence), None)
            if ckpt is not None:
                ckpt.verify()
        if ckpt is None:
            raise SavePlaneError("no restorable save",
                                 context={"slot": slot, "sequence": sequence})
        state = self._migrate(json.loads(_canon(ckpt.state)))
        receipts = None
        if "receipts" in state:
            receipts = ChunkReceiptStore.from_state(state["receipts"])
            if receipts.root() != state.get("receipt_root"):
                raise SavePlaneError("receipt root mismatch",
                                     context={"slot": slot})
        return state["sections"], receipts

    def backups(self, slot: str) -> Tuple[int, ...]:
        return tuple(c.sequence for c in self.store.history(self._component(slot)))


# --------------------------------------------------------------------------
# Replay journal + bounded AI-context cursor (GF-P0-117)
# --------------------------------------------------------------------------

Reducer = Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]


class ReplayJournal:
    def __init__(self, *, context_window: int = 64) -> None:
        if context_window < 1:
            raise SavePlaneError("context_window must be >= 1")
        self.context_window = context_window
        self._frames: Dict[int, Tuple[str, Dict[str, Any]]] = {}

    def append(self, frame: int, event: Mapping[str, Any]) -> str:
        event = dict(event)
        digest = content_digest(event)
        prior = self._frames.get(frame)
        if prior is not None:
            if prior[0] == digest:
                return digest
            raise ReplayConflictError("frame already recorded with different event",
                                      context={"frame": frame})
        self._frames[frame] = (digest, event)
        return digest

    def frames(self, *, after: int = -1) -> List[Tuple[int, Dict[str, Any]]]:
        return [(f, self._frames[f][1]) for f in sorted(self._frames) if f > after]

    def ai_context(self, *, upto: Optional[int] = None) -> List[Dict[str, Any]]:
        keys = sorted(f for f in self._frames if upto is None or f <= upto)
        return [self._frames[f][1] for f in keys[-self.context_window:]]

    def replay(self, base: Mapping[str, Any], reducer: Reducer,
               *, after: int = -1, upto: Optional[int] = None) -> Dict[str, Any]:
        state = json.loads(_canon(dict(base)))
        for f, ev in self.frames(after=after):
            if upto is not None and f > upto:
                break
            state = reducer(state, ev)
        return state

    def head_digest(self) -> str:
        return content_digest([self._frames[f][0] for f in sorted(self._frames)])


__all__ = [
    "SAVE_SCHEMA_VERSION", "SavePlaneError", "ReplayConflictError",
    "content_digest", "ChunkReceipt", "ReceiptPage", "ChunkReceiptStore",
    "GameSavePlane", "ReplayJournal",
]
