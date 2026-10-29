"""Loot roller.
Rolls value, rarity, and effect from source type and optical.
"""
from typing import Any, Dict

class LootRoller:
    SOURCES = {"pack": 8, "elite": 15, "boss": 30, "rift": 25}

    def roll(self, source: str, optical: float) -> Dict[str, Any]:
        base = self.SOURCES.get(source, 5)
        value = int(base * (1.0 + optical * 0.5))
        rarity = "rare" if optical > 0.9 else "uncommon" if optical > 0.7 else "common"
        effect = "armor" if source == "elite" else "speed" if source == "pack" else "optical"
        return {
            "source": source,
            "value": value,
            "rarity": rarity,
            "effect": effect,
            "optical": optical,
            "schema": "skeleton.loot.roller.v1",
        }
