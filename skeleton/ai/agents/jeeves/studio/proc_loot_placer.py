"""Place procedural loot with optical bias."""
from __future__ import annotations
from typing import Dict, Any

def place_loot(rooms: int, optical: float) -> Dict[str, Any]:
    if rooms < 1 or optical < 0.8:
        return {"ok": False, "reason": "floors", "placed": 0}
    placed = max(1, int(rooms * optical * 0.5))
    return {"ok": True, "rooms": rooms, "placed": placed, "optical": optical, "reason": "ok"}
