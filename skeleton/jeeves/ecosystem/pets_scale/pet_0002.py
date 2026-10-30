"""Pet scale 0002.
"""
from __future__ import annotations

ID = "pet_scale_0002"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "value": 10 + 2}

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "id": ID, "player": player, "granted": True}
