"""Loot table.
Rolls salvage and items from pack clears, elite kills, and boss phases.
"""
from __future__ import annotations
from typing import Any, Dict, List
import random

class LootTable:
    def __init__(self, seed: int = 8847291):
        self.rng = random.Random(seed)
    def roll(self, source: str, difficulty: float = 1.0, optical: float = 0.9) -> Dict[str, Any]:
        base = {"pack": 8, "elite": 18, "boss": 40, "rift": 25}.get(source, 5)
        value = int(base * difficulty * (0.8 + optical * 0.4))
        rarity = "common"
        if self.rng.random() < 0.15 + optical * 0.1:
            rarity = "rare"
        if source == "boss" and self.rng.random() < 0.3:
            rarity = "epic"
        return {
            "source": source,
            "value": value,
            "rarity": rarity,
            "effect": self.rng.choice(["speed", "armor", "range", "salvage_rate"]),
            "optical_tag": "loot",
        }
