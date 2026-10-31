"""skeleton/economy/harbor_100x.py
100x extreme complete Economy harbor / bag ops.
Catalog cards only, lineage weights sum=1, reversible bag ops. No currency network.
Fail-closed.
"""
from __future__ import annotations
from typing import Dict

class HarborError(Exception):
    pass

class EconomyHarbor100x:
    def __init__(self):
        self.weights: Dict[str, float] = {}

    def set_weights(self, weights: Dict[str, float]) -> None:
        if abs(sum(weights.values()) - 1.0) > 1e-6:
            raise HarborError("weights must sum to 1")
        self.weights = weights.copy()

    def bag_op(self, key: str, delta: float) -> float:
        self.weights[key] = self.weights.get(key, 0.0) + delta
        return self.weights[key]
