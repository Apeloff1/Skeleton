"""The fabric — a hash-chained event spine for the Python courts.

Same law as the Rust Ω-fabric: append-only, every event carries
prev_hash, and verify() walks genesis to head. Events journal to the
outbox before they are admitted to the hot tail — durability precedes
observability.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any

from .outbox import Outbox

GENESIS = "genesis"


@dataclass
class FabricEvent:
    id: str
    ledger: str
    kind: str
    payload: dict[str, Any]
    ts: float
    seq: int
    quorum: list[str]
    prev_hash: str
    hash: str = ""

    def canonical(self) -> str:
        return "|".join([
            str(self.seq), self.ledger, self.kind,
            _stable_json(self.payload), f"{self.ts:.6f}",
            ",".join(self.quorum), self.prev_hash,
        ])

    def compute_hash(self) -> str:
        return hashlib.sha256(self.canonical().encode("utf-8")).hexdigest()


def _stable_json(v: Any) -> str:
    import json
    return json.dumps(v, sort_keys=True, separators=(",", ":"))


class ChainBroken(Exception):
    pass


class Fabric:
    def __init__(self, outbox: Outbox, hot_cap: int = 2048):
        self._outbox = outbox
        self._hot_cap = hot_cap
        self._tail: list[FabricEvent] = []
        self._seq = 0
        self._head = GENESIS
        self._lock = asyncio.Lock()

    async def append(self, ledger: str, kind: str,
                     payload: dict[str, Any], quorum: list[str]) -> FabricEvent:
        async with self._lock:
            self._seq += 1
            ev = FabricEvent(
                id=str(uuid.uuid4()), ledger=ledger, kind=kind,
                payload=payload, ts=time.time(), seq=self._seq,
                quorum=list(quorum), prev_hash=self._head,
            )
            ev.hash = ev.compute_hash()
            try:
                # Journal FIRST. If the outbox refuses, the event never was.
                await self._outbox.journal("omega_fabric", asdict(ev))
            except Exception:
                self._seq -= 1  # roll the chain back — no ghost events
                raise
            self._head = ev.hash
            if len(self._tail) >= self._hot_cap:
                del self._tail[: self._hot_cap // 4]
            self._tail.append(ev)
            return ev

    async def verify(self) -> bool:
        prev = GENESIS
        async with self._lock:
            for ev in self._tail:
                if ev.prev_hash != prev:
                    raise ChainBroken(f"seq {ev.seq}: prev_hash does not chain")
                if ev.hash != ev.compute_hash():
                    raise ChainBroken(f"seq {ev.seq}: hash does not match content")
                prev = ev.hash
        return True

    async def tail(self, ledger: str, limit: int = 128) -> list[FabricEvent]:
        async with self._lock:
            return [e for e in reversed(self._tail) if e.ledger == ledger][:limit]

    @property
    def head(self) -> str:
        return self._head
