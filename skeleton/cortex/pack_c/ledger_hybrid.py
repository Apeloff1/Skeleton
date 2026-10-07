"""Hybrid thought ledger — coalesce tapes without clobbering neo state."""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple
import time


@dataclass(frozen=True)
class LedgerEntry:
    entry_id: str
    slot: str
    kind: str
    text: str
    tags: Tuple[str, ...]
    numbers: Tuple[float, ...] = ()
    ts: float = 0.0
    parent: Optional[str] = None

    def digest(self) -> str:
        raw = f"{self.entry_id}|{self.slot}|{self.kind}|{self.text}|{','.join(self.tags)}"
        return sha256(raw.encode()).hexdigest()[:16]


@dataclass
class HybridLedger:
    max_entries: int = 4096
    _items: List[LedgerEntry] = field(default_factory=list)
    _by_id: Dict[str, LedgerEntry] = field(default_factory=dict)

    def append(self, entry: LedgerEntry) -> LedgerEntry:
        if entry.entry_id in self._by_id:
            return self._by_id[entry.entry_id]
        if len(self._items) >= self.max_entries:
            old = self._items.pop(0)
            self._by_id.pop(old.entry_id, None)
        self._items.append(entry)
        self._by_id[entry.entry_id] = entry
        return entry

    def coalesce(self, slot: str, *, limit: int = 32) -> str:
        parts = [e.text for e in self._items if e.slot == slot and e.text][-limit:]
        return " | ".join(parts)

    def kinds(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for e in self._items:
            out[e.kind] = out.get(e.kind, 0) + 1
        return out

    def filter_own(self) -> List[LedgerEntry]:
        return [e for e in self._items if e.kind == "own"]

    def snapshot(self) -> dict[str, Any]:
        return {
            "count": len(self._items),
            "kinds": self.kinds(),
            "digests": [e.digest() for e in self._items[-64:]],
        }


def mint_entry(i: int, *, slot: str = "neo", kind: str = "own") -> LedgerEntry:
    return LedgerEntry(
        entry_id=f"led-{i:05d}",
        slot=slot,
        kind=kind,
        text=f"ledger tape {i:05d}",
        tags=("pack_c", "ledger", kind),
        numbers=(float(i % 13), float(i % 7)),
        ts=time.time(),
    )


LEDGER_SEED: Tuple[Mapping[str, Any], ...] = tuple(
    {
        "i": i,
        "slot": ("pfc", "midbrain", "neo")[i % 3],
        "kind": "own" if i % 5 else "own-lm",
    }
    for i in range(1, 801)
)


def seed_ledger(ledger: Optional[HybridLedger] = None) -> HybridLedger:
    led = ledger or HybridLedger()
    for row in LEDGER_SEED:
        led.append(mint_entry(int(row["i"]), slot=str(row["slot"]), kind=str(row["kind"])))
    return led
