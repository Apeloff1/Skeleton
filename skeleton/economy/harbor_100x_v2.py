"""skeleton/economy/harbor_100x_v2.py
Further 100x extreme Economy harbor / bag ops.
Catalog cards only, lineage weights sum=1, reversible bag. No coin.
Fail-closed.
"""
from __future__ import annotations
from typing import Dict

class HarborError(Exception):
    pass

class EconomyHarbor100xV2:
    def __init__(self):
        self.weights: Dict[str, float] = {}

    def set_weights(self, weights: Dict[str, float]) -> None:
        s = sum(weights.values())
        if abs(s - 1.0) > 1e-9:
            raise HarborError("weights must sum to 1")
        self.weights = {k: v for k, v in weights.items()}

    def bag_op(self, key: str, delta: float) -> float:
        self.weights[key] = max(0.0, self.weights.get(key, 0.0) + delta)
        return self.weights[key]
