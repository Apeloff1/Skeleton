"""Roll loot with optical rarity bias."""
from __future__ import annotations
from typing import Dict, Any

def roll_loot(source: str, optical: float) -> Dict[str, Any]:
    if optical < 0.7 or not source:
        return {"ok": False, "reason": "floors", "rarity": "common"}
    rarity = "rare" if optical > 0.88 else "uncommon" if optical > 0.75 else "common"
    return {"ok": True, "source": source, "rarity": rarity, "optical": optical, "value": int(optical * 100), "reason": "ok"}
