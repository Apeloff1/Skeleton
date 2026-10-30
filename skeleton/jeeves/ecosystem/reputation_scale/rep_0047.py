"""Rep scale 0047.
"""
from __future__ import annotations

ID = "rep_scale_0047"

def describe() -> dict:
    return {"id": ID, "kind": "rep", "value": 10 + 47}

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "id": ID, "player": player, "granted": True}
