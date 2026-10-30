"""Title scale 0058.
"""
from __future__ import annotations

ID = "title_scale_0058"

def describe() -> dict:
    return {"id": ID, "kind": "title", "value": 10 + 58}

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "id": ID, "player": player, "granted": True}
