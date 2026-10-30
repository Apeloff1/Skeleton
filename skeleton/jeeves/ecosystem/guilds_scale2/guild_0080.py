"""Guild advanced 0080.
"""
from __future__ import annotations

ID = "guild_adv_0080"

def describe() -> dict:
    return {"id": ID, "kind": "guild", "value": 10 + 80}

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "id": ID, "player": player, "granted": True}
