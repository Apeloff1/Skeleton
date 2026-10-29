"""All-in optical loot roller."""
from __future__ import annotations
from typing import Dict, Any

def loot_allin(source: str, optical: float) -> Dict[str, Any]:
    if not source or optical < 0.7:
        return {"ok": False, "reason": "floors", "rarity": "common"}
    rarity = "epic" if optical > 0.95 else "rare" if optical > 0.88 else "uncommon" if optical > 0.75 else "common"
    return {"ok": True, "source": source, "rarity": rarity, "optical": optical, "reason": "ok"}
