"""Title scale 0031.
"""
from __future__ import annotations

ID = "title_scale_0031"

def describe() -> dict:
    return {"id": ID, "kind": "title", "value": 10 + 31}

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "id": ID, "player": player, "granted": True}
