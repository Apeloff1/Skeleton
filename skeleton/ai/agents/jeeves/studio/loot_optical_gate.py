"""Optical gate for loot rarity."""
from __future__ import annotations
from typing import Dict, Any

def gate_loot(optical: float) -> Dict[str, Any]:
    if optical < 0.75:
        return {"ok": False, "reason": "floors", "rarity": "common"}
    rarity = "epic" if optical > 0.95 else "rare" if optical > 0.88 else "uncommon"
    return {"ok": True, "rarity": rarity, "optical": optical, "reason": "ok"}
