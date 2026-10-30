"""House advanced 0012.
"""
from __future__ import annotations

ID = "house_adv_0012"

def describe() -> dict:
    return {"id": ID, "kind": "house", "value": 10 + 12}

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "id": ID, "player": player, "granted": True}
