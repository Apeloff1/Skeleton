"""Loot table 0006.
"""
from __future__ import annotations

TABLE = "loot_0006"

def roll(optical: float = 0.9) -> dict:
    if optical > 0.95:
        rarity = "epic"
    elif optical > 0.9:
        rarity = "rare"
    else:
        rarity = "common"
    return {"ok": True, "table": TABLE, "rarity": rarity, "item": f"drop_{6}"}
