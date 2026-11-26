"""Transactional source of truth for the historical Zaibatsu event spine.

V2 hashes every identity-bearing field using canonical JSON. It deliberately
does not claim byte parity with the earlier delimiter-based Rust format.
Legacy external sink history requires a separately verified migration.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any

from .outbox import GENESIS, JournalIntegrityError, Outbox, canonical, _name


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
    format: int = 2

    def canonical(self) -> str:
        fields = asdict(self)
        fields.pop("hash")
        return canonical(fields)

    def compute_hash(self) -> str:
        return hashlib.sha256(self.canonical().encode("ascii")).hexdigest()


class ChainBroken(JournalIntegrityError):
    pass


def validate_event(doc: dict, *, seq: int | None = None, prev: str | None = None) -> None:
    try:
        ev = FabricEvent(**doc)
        if type(ev.format) is not int or ev.format != 2:
            raise ValueError("unknown fabric version")
        if str(uuid.UUID(ev.id)) != ev.id:
            raise ValueError("invalid event ID")
        _name(ev.ledger)
        _name(ev.kind)
        if type(ev.seq) is not int or ev.seq < 1 or (seq is not None and ev.seq != seq):
            raise ValueError("invalid event sequence")
        if type(ev.ts) not in (int, float) or not math.isfinite(ev.ts) or ev.ts <= 0:
            raise ValueError("invalid event time")
        if type(ev.payload) is not dict or type(ev.quorum) is not list or len(ev.quorum) > 128:
            raise ValueError("invalid event body")
        if len(set(ev.quorum)) != len(ev.quorum):
            raise ValueError("duplicate quorum identity")
        for member in ev.quorum:
            _name(member)
        if prev is not None and ev.prev_hash != prev:
            raise ValueError("previous hash mismatch")
        if ev.seq == 1 and ev.prev_hash != GENESIS:
            raise ValueError("invalid genesis")
        if ev.seq > 1 and (len(ev.prev_hash) != 64 or any(c not in "0123456789abcdef" for c in ev.prev_hash)):
            raise ValueError("invalid previous hash")
        if type(ev.hash) is not str or not hmac.compare_digest(ev.compute_hash(), ev.hash):
            raise ValueError("event hash mismatch")
    except (TypeError, ValueError, AttributeError, OverflowError) as exc:
        raise ChainBroken("fabric event integrity verification failed") from exc


class Fabric:
    """Bounded hot view backed by the complete retained durable history."""

    def __init__(self, outbox: Outbox, hot_cap: int = 2048):
        if type(hot_cap) is not int or not 1 <= hot_cap <= 10000:
            raise ValueError("invalid hot-tail capacity")
        self._outbox = outbox
        self._hot_cap = hot_cap
        self._outbox.verify_fabric()

    async def append(self, ledger: str, kind: str,
                     payload: dict[str, Any], quorum: list[str]) -> FabricEvent:
        # Copy before admission to prevent later caller mutations becoming
        # unjournaled edits. Strict canonicalization rejects NaN and objects.
        if type(payload) is not dict or type(quorum) is not list:
            raise ValueError("invalid fabric payload")
        payload = json.loads(canonical(payload))
        quorum = list(quorum)
        def factory(seq: int, previous: str) -> dict:
            ev = FabricEvent(id=str(uuid.uuid4()), ledger=ledger, kind=kind,
                             payload=payload, ts=time.time(), seq=seq,
                             quorum=quorum, prev_hash=previous)
            ev.hash = ev.compute_hash()
            return asdict(ev)
        return FabricEvent(**self._outbox.append_fabric(factory))

    async def verify(self) -> bool:
        return self._outbox.verify_fabric()

    async def tail(self, ledger: str, limit: int = 128) -> list[FabricEvent]:
        _name(ledger)
        if type(limit) is not int or not 1 <= limit <= 10000:
            raise ValueError("invalid tail limit")
        return [FabricEvent(**doc) for doc in self._outbox.fabric_tail(ledger, limit, self._hot_cap)]

    @property
    def head(self) -> str:
        return self._outbox.health()["fabric_head"]
