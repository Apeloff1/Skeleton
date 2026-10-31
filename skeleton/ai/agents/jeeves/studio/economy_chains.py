"""Dynamic economy chains (10x).
Salvage sources, spend sinks, upgrade trees that modify player stats, market fluctuation.
"""
from __future__ import annotations
from typing import Any, Dict, List

class EconomyChain:
    def __init__(self):
        self.salvage = 0
        self.upgrades = {}
        self.market_mult = 1.0

    def harvest(self, source: str, amount: int) -> int:
        bonus = 1.2 if source == "boss" else 1.0
        self.salvage += int(amount * bonus * self.market_mult)
        return self.salvage

    def invest(self, upgrade: str, cost: int) -> bool:
        if self.salvage < cost:
            return False
        self.salvage -= cost
        self.upgrades[upgrade] = self.upgrades.get(upgrade, 0) + 1
        self.market_mult = max(0.7, self.market_mult - 0.02)
        return True

    def player_modifiers(self) -> Dict[str, float]:
        return {
            "speed": 1.0 + self.upgrades.get("speed", 0) * 0.12,
            "armor": self.upgrades.get("armor", 0) * 6.0,
            "range": 1.0 + self.upgrades.get("range", 0) * 0.08,
        }

    def status(self) -> Dict[str, Any]:
        return {"salvage": self.salvage, "upgrades": self.upgrades, "market": round(self.market_mult, 2)}
