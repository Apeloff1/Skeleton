"""Emote advanced 0030.
"""
from __future__ import annotations

ID = "emote_adv_0030"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "value": 10 + 30}

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "id": ID, "player": player, "granted": True}
