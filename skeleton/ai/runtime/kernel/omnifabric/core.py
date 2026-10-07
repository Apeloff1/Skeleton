"""OmniFabric — Ω-fabric hash-chained event spine (gameforge-rs port).

Sibling source: ``Apeloff1/gameforge-rs``
``crates/gf-gameforge/src/lib.rs`` ``pub mod fabric`` / ``OmniFabric``.

Doctrine:
- Append-only, quorum-tagged, outbox-journaled, hash-chained
- Journal FIRST; if the outbox refuses, the event never was
- Hot tail for read-your-writes; capacity drains oldest quarter when full
- ``verify_chain`` recomputes genesis→head — tampering yields evidence

This is the hex OmniFabric. It does **not** replace
``backend.zaibatsu.fabric.Fabric`` — that backend path stays untouched.
Callers that need the skeleton hex surface import from here.
"""
from __future__ import annotations

import threading
from typing import Any, Iterable, Mapping, Sequence

from skeleton.kernel.omnifabric.codecs import GENESIS_HASH
from skeleton.kernel.omnifabric.errors import ChainBroken, OutboxFull, OutboxJournalError
from skeleton.kernel.omnifabric.events import FabricEvent, event_to_mapping
from skeleton.kernel.omnifabric.outbox import COLLECTION_DEFAULT, FabricOutbox

__all__ = ["OmniFabric", "DEFAULT_HOT_CAP"]

DEFAULT_HOT_CAP = 2048


class OmniFabric:
    """The Ω-fabric: append-only, quorum-gated, outbox-journaled, hash-chained.

    Thread-safe via an RLock around seq/head/tail mutations. Async callers
    may wrap ``append`` / ``verify_chain`` in ``asyncio.to_thread``; the RS
    original is async over RwLock — the hex port prefers sync+lock to match
    other skeleton.kernel modules (court, saga).
    """

    def __init__(
        self,
        outbox: FabricOutbox | None = None,
        *,
        hot_cap: int = DEFAULT_HOT_CAP,
        collection: str = COLLECTION_DEFAULT,
        auto_confirm: bool = True,
    ) -> None:
        if hot_cap < 1:
            raise ValueError("hot_cap must be >= 1")
        self._outbox = outbox if outbox is not None else FabricOutbox()
        self._hot_cap = int(hot_cap)
        self._collection = str(collection)
        self._auto_confirm = bool(auto_confirm)
        self._tail: list[FabricEvent] = []
        self._seq = 0
        self._head = GENESIS_HASH
        self._lock = threading.RLock()
        self._appends = 0
        self._rollbacks = 0
        self._drains = 0

    # -- introspection -----------------------------------------------------

    @property
    def outbox(self) -> FabricOutbox:
        return self._outbox

    @property
    def hot_cap(self) -> int:
        return self._hot_cap

    @property
    def head_hash(self) -> str:
        with self._lock:
            return self._head

    @property
    def current_seq(self) -> int:
        with self._lock:
            return self._seq

    @property
    def hot_len(self) -> int:
        with self._lock:
            return len(self._tail)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "seq": self._seq,
                "head_hash": self._head,
                "hot_len": len(self._tail),
                "hot_cap": self._hot_cap,
                "appends": self._appends,
                "rollbacks": self._rollbacks,
                "drains": self._drains,
                "outbox_pending": self._outbox.pending_count(),
                "outbox_journaled": self._outbox.journaled_total,
                "outbox_confirmed": self._outbox.confirmed_total,
            }

    # -- mutate ------------------------------------------------------------

    def append(
        self,
        ledger: str,
        kind: str,
        payload: Mapping[str, Any] | None = None,
        quorum: Sequence[str] | Iterable[str] | None = None,
        *,
        event_id: str | None = None,
        ts: float | None = None,
    ) -> FabricEvent:
        """Append an event. Order is law: journal → hot tail → optional confirm.

        Raises ``OutboxFull`` / ``OutboxJournalError`` without admitting the
        event to the hot tail (seq and head roll back).
        """
        quorum_list = list(quorum or [])
        with self._lock:
            self._seq += 1
            ev = FabricEvent.create(
                ledger=ledger,
                kind=kind,
                payload=payload,
                seq=self._seq,
                quorum=quorum_list,
                prev_hash=self._head,
                event_id=event_id,
                ts=ts,
            )
            try:
                jseq = self._outbox.journal(self._collection, event_to_mapping(ev))
            except (OutboxFull, OutboxJournalError):
                self._seq -= 1
                self._rollbacks += 1
                raise
            except Exception as exc:  # noqa: BLE001
                self._seq -= 1
                self._rollbacks += 1
                raise OutboxJournalError(str(exc)) from exc

            self._head = ev.hash
            if len(self._tail) >= self._hot_cap:
                drain = max(1, self._hot_cap // 4)
                del self._tail[:drain]
                self._drains += 1
            self._tail.append(ev)
            self._appends += 1

        if self._auto_confirm:
            try:
                self._outbox.confirm_one(jseq)
            except OutboxJournalError:
                # reconciler covers failure — event is already journaled+hot
                pass
        return ev

    # -- verify / read -----------------------------------------------------

    def verify_chain(self) -> bool:
        """Verify the hash chain across the hot tail.

        Returns True on success. Raises ``ChainBroken(seq, detail)`` with
        evidence on divergence (RS returns ``Err((seq, String))``).
        """
        with self._lock:
            prev = GENESIS_HASH
            # If the hot tail was drained, the first remaining event may not
            # chain from genesis — verify contiguous integrity of what we hold.
            if self._tail:
                # Allow non-genesis prev only when seq > 1 and we drained.
                # Contiguous check: each event's prev_hash equals prior hash,
                # and each hash matches content. First event may start mid-chain
                # after a drain; we still check self-hash and successor links.
                first = self._tail[0]
                if first.seq == 1 and first.prev_hash != GENESIS_HASH:
                    raise ChainBroken(first.seq, f"prev_hash mismatch: expected {GENESIS_HASH}, got {first.prev_hash}")
                if first.seq == 1:
                    prev = GENESIS_HASH
                else:
                    prev = first.prev_hash
            for ev in self._tail:
                if ev.prev_hash != prev:
                    raise ChainBroken(
                        ev.seq,
                        f"prev_hash mismatch: expected {prev}, got {ev.prev_hash}",
                    )
                if ev.hash != ev.compute_hash():
                    raise ChainBroken(ev.seq, "event hash does not match its content")
                prev = ev.hash
            return True

    def verify_full_from_genesis(self) -> bool:
        """Strict genesis→head verify — requires seq 1 still in the hot tail."""
        with self._lock:
            if not self._tail:
                return True
            if self._tail[0].seq != 1 or self._tail[0].prev_hash != GENESIS_HASH:
                raise ChainBroken(
                    self._tail[0].seq,
                    "hot tail no longer holds genesis; use verify_chain() or sealed segments",
                )
        return self.verify_chain()

    def tail(self, ledger: str, limit: int = 128) -> list[FabricEvent]:
        """Newest-first events for ``ledger``, capped at ``limit``."""
        if limit < 0:
            raise ValueError("limit must be >= 0")
        with self._lock:
            out: list[FabricEvent] = []
            for ev in reversed(self._tail):
                if ev.ledger == ledger:
                    out.append(ev)
                    if len(out) >= limit:
                        break
            return out

    def tail_all(self, limit: int = 128) -> list[FabricEvent]:
        with self._lock:
            if limit <= 0:
                return []
            return list(reversed(self._tail[-limit:]))

    def get_by_seq(self, seq: int) -> FabricEvent | None:
        with self._lock:
            for ev in self._tail:
                if ev.seq == seq:
                    return ev
            return None

    def snapshot_tail(self) -> list[FabricEvent]:
        with self._lock:
            return list(self._tail)
