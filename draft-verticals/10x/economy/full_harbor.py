"""Full economy harbor: cards only, lineage weights sum=1, reversible bag ops, no currency.
"""
from dataclasses import dataclass, field
from typing import List, Dict

@dataclass
class Card:
    id: str
    name: str
    weight: float
    lineage: List[str] = field(default_factory=list)
    ops: List[str] = field(default_factory=list)

class FullHarbor:
    def __init__(self):
        self.bag: List[Card] = []

    def add(self, card: Card):
        self.bag.append(card)
        self._normalize()

    def _normalize(self):
        total = sum(c.weight for c in self.bag) or 1
        for c in self.bag:
            c.weight /= total

    def reverse(self, cid: str, op: str) -> bool:
        for c in self.bag:
            if c.id == cid and op in c.ops:
                c.ops.remove(op)
                return True
        return False

    def catalog(self) -> List[Dict]:
        return [{"id": c.id, "weight": c.weight, "lineage": c.lineage} for c in self.bag]
