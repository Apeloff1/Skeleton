"""FabricEvent — one immutable fact in the omnifabric.

Port of gameforge-rs ``fabric::FabricEvent``. Events are the only truth;
projections are derived, disposable, rebuildable. F5: every event chains
to its predecessor via ``prev_hash``; tampering breaks every head after it.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping

from skeleton.kernel.omnifabric.codecs import GENESIS_HASH, sha256_hex, stable_json

__all__ = [
    "GENESIS_HASH",
    "FabricEvent",
    "event_from_mapping",
    "event_to_mapping",
]


@dataclass
class FabricEvent:
    """One immutable fact in the Ω-fabric.

    Fields match RS ``fabric::FabricEvent``. ``hash`` is computed over the
    canonical form and never covers itself.
    """

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
        """Fixed-order hashing form — every field that makes the event.

        Order matches RS: seq|ledger|kind|payload|ts|quorum|prev_hash.
        Payload uses stable JSON; ts uses 6-decimal float for Python parity
        with the zaibatsu Fabric sibling (RS uses RFC3339 — both are stable
        within their runtime).
        """
        return "|".join(
            [
                str(self.seq),
                self.ledger,
                self.kind,
                stable_json(self.payload),
                f"{self.ts:.6f}",
                ",".join(self.quorum),
                self.prev_hash,
            ]
        )

    def compute_hash(self) -> str:
        return sha256_hex(self.canonical())

    def seal(self) -> "FabricEvent":
        """Return self with ``hash`` set from canonical content."""
        self.hash = self.compute_hash()
        return self

    def verify_self(self) -> bool:
        return bool(self.hash) and self.hash == self.compute_hash()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def create(
        cls,
        *,
        ledger: str,
        kind: str,
        payload: Mapping[str, Any] | None,
        seq: int,
        quorum: Iterable[str],
        prev_hash: str,
        event_id: str | None = None,
        ts: float | None = None,
    ) -> "FabricEvent":
        ev = cls(
            id=event_id or str(uuid.uuid4()),
            ledger=str(ledger),
            kind=str(kind),
            payload=dict(payload or {}),
            ts=float(time.time() if ts is None else ts),
            seq=int(seq),
            quorum=list(quorum),
            prev_hash=str(prev_hash),
        )
        return ev.seal()


def event_to_mapping(ev: FabricEvent) -> dict[str, Any]:
    return ev.to_dict()


def event_from_mapping(data: Mapping[str, Any]) -> FabricEvent:
    return FabricEvent(
        id=str(data["id"]),
        ledger=str(data["ledger"]),
        kind=str(data["kind"]),
        payload=dict(data.get("payload") or {}),
        ts=float(data["ts"]),
        seq=int(data["seq"]),
        quorum=list(data.get("quorum") or []),
        prev_hash=str(data["prev_hash"]),
        hash=str(data.get("hash") or ""),
    )
