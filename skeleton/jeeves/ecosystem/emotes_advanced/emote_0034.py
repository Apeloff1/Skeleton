"""Emote advanced 0034.
"""
from __future__ import annotations

ID = "emote_adv_0034"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "value": 10 + 34}

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "id": ID, "player": player, "granted": True}
