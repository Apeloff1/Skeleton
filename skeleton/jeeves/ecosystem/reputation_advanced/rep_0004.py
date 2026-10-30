"""Rep advanced 0004.
"""
from __future__ import annotations

ID = "rep_adv_0004"

def describe() -> dict:
    return {"id": ID, "kind": "rep", "value": 10 + 4}

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "id": ID, "player": player, "granted": True}
