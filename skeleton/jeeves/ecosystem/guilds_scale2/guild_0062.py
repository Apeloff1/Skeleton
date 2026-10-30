"""Guild advanced 0062.
"""
from __future__ import annotations

ID = "guild_adv_0062"

def describe() -> dict:
    return {"id": ID, "kind": "guild", "value": 10 + 62}

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "id": ID, "player": player, "granted": True}
