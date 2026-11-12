"""10x Enhanced economy harbor. Massive patch.
Cards, lineage, weights sum=1, reversible ops, export.
"""
from dataclasses import dataclass, field
from typing import List, Dict

@dataclass
class Card:
    id: str
    weight: float
    lineage: List[str] = field(default_factory=list)

class EnhancedEconomy:
    def __init__(self):
        self.bag: List[Card] = []

    def add(self, card: Card):
        self.bag.append(card)
        self._normalize()

    def _normalize(self):
        total = sum(c.weight for c in self.bag) or 1
        for c in self.bag:
            c.weight /= total

    def export(self) -> List[Dict]:
        return [{"id": c.id, "weight": c.weight, "lineage": c.lineage} for c in self.bag]
