"""Guild scale 0086.
"""
from __future__ import annotations

ID = "guild_scale_0086"

def describe() -> dict:
    return {"id": ID, "kind": "guild", "value": 10 + 86}

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "id": ID, "player": player, "granted": True}
