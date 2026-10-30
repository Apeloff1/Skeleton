"""Pet scale 0013.
"""
from __future__ import annotations

ID = "pet_scale_0013"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "value": 10 + 13}

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "id": ID, "player": player, "granted": True}
