"""Rep scale 0078.
"""
from __future__ import annotations

ID = "rep_scale_0078"

def describe() -> dict:
    return {"id": ID, "kind": "rep", "value": 10 + 78}

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "id": ID, "player": player, "granted": True}
