"""Emote advanced 0038.
"""
from __future__ import annotations

ID = "emote_adv_0038"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "value": 10 + 38}

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "id": ID, "player": player, "granted": True}
