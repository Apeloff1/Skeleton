"""Title scale 0065.
"""
from __future__ import annotations

ID = "title_scale_0065"

def describe() -> dict:
    return {"id": ID, "kind": "title", "value": 10 + 65}

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "id": ID, "player": player, "granted": True}
