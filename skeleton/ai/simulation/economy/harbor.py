"""Bag + harbor. Lineage weights sum to 1. Ops reversible. No coin."""

from __future__ import annotations

from skeleton.economy.law import EPS


class Harbor:
    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self.bag: list[str] = []
        self.weights = dict(weights or {"house": 1.0})
        self._undo: list[tuple[str, str]] = []

    def put(self, item: str) -> None:
        self.bag.append(item)
        self._undo.append(("put", item))

    def take(self, item: str) -> bool:
        if item not in self.bag:
            return False
        self.bag.remove(item)
        self._undo.append(("take", item))
        return True

    def undo(self) -> bool:
        if not self._undo:
            return False
        op, item = self._undo.pop()
        if op == "put" and item in self.bag:
            self.bag.remove(item)
        elif op == "take":
            self.bag.append(item)
        return True

    def set_weights(self, weights: dict[str, float]) -> None:
        self.weights = dict(weights)

    def weight_sum(self) -> float:
        return float(sum(self.weights.values()))

    def balanced(self) -> bool:
        return abs(self.weight_sum() - 1.0) <= EPS

    def card(self) -> dict:
        return {
            "kind": "economy",
            "bag": list(self.bag),
            "harbor": "catalog",
            "weights": dict(self.weights),
            "sum": self.weight_sum(),
            "coin": 0,
            "stored_prose": 0,
        }
