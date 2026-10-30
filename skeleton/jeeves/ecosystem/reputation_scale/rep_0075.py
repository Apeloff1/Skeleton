"""Rep scale 0075.
"""
from __future__ import annotations

ID = "rep_scale_0075"

def describe() -> dict:
    return {"id": ID, "kind": "rep", "value": 10 + 75}

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "id": ID, "player": player, "granted": True}
