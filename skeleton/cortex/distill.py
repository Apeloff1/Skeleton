"""Distillation — Jeeves acquires a slot's abilities into its own system.

Every thought is a training pair (stimulus fingerprint → ability).
acquire(slot) copies that tract into the neocortex ledger. surpass(slot)
arms own-system answers for that tract. Nearest-neighbour on the
fingerprint is the few-shot recall; no gradient, no weights.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from skeleton.cortex.port import Thought, fingerprint


@dataclass
class Ability:
    slot: str
    stimulus_fp: str
    signature: str
    kind: str
    text: str
    tags: Tuple[str, ...]
    numbers: Tuple[float, ...]
    confidence: float
    seen: int = 1

    def to_dict(self) -> dict:
        return {
            "slot": self.slot,
            "stimulus_fp": self.stimulus_fp,
            "signature": self.signature,
            "kind": self.kind,
            "text": self.text,
            "tags": list(self.tags),
            "numbers": list(self.numbers),
            "confidence": round(self.confidence, 4),
            "seen": self.seen,
        }

    def as_thought(self) -> Thought:
        return Thought(
            slot=self.slot, kind=self.kind, text=self.text,
            confidence=self.confidence, tags=self.tags, numbers=self.numbers,
            signature=self.signature,
        )


def ability_from(thought: Thought, stimulus: str) -> Ability:
    return Ability(
        slot=thought.slot,
        stimulus_fp=fingerprint(stimulus),
        signature=thought.signature,
        kind=thought.kind,
        text=thought.text,
        tags=thought.tags,
        numbers=thought.numbers,
        confidence=thought.confidence,
    )


class AbilityLedger:
    """Append-only training log keyed by (slot, stimulus_fp)."""

    def __init__(self) -> None:
        self._items: List[Ability] = []
        self._by: Dict[Tuple[str, str], Ability] = {}

    def record(self, thought: Thought, stimulus: str) -> Ability:
        ab = ability_from(thought, stimulus)
        key = (ab.slot, ab.stimulus_fp)
        prev = self._by.get(key)
        if prev is not None:
            ab.seen = prev.seen + 1
        self._by[key] = ab
        self._items.append(ab)
        return ab

    def of_slot(self, slot: str) -> List[Ability]:
        return [a for a in self._by.values() if a.slot == slot]

    def get(self, slot: str, stim_fp: str) -> Optional[Ability]:
        return self._by.get((slot, stim_fp))

    def nearest(self, stim_fp: str, *, slot: Optional[str] = None) -> Optional[Ability]:
        pool = [a for a in self._by.values() if slot is None or a.slot == slot]
        if not pool:
            return None
        # hex hamming on the 16-char fingerprint
        def dist(a: Ability) -> int:
            return sum(x != y for x, y in zip(a.stimulus_fp, stim_fp))
        return min(pool, key=dist)

    @property
    def size(self) -> int:
        return len(self._by)

    def to_dict(self) -> dict:
        return {"size": self.size, "events": len(self._items)}
