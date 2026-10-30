"""Pet advanced 0003.
"""
from __future__ import annotations

ID = "pet_adv_0003"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "value": 10 + 3}

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "id": ID, "player": player, "granted": True}
