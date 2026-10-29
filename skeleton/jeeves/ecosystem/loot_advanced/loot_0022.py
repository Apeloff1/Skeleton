"""Advanced loot 0022.
"""
from __future__ import annotations

LOOT = "adv_loot_0022"

def roll(optical: float = 0.9, luck: float = 0.0) -> dict:
    score = optical + luck
    rarity = "epic" if score > 1.1 else ("rare" if score > 0.95 else "common")
    return {"ok": True, "loot": LOOT, "rarity": rarity, "item": f"drop_{22}"}
