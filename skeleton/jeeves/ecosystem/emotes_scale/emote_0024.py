"""Emote scale 0024.
"""
from __future__ import annotations

ID = "emote_scale_0024"

def describe() -> dict:
    return {"id": ID, "kind": "emote", "value": 10 + 24}

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "id": ID, "player": player, "granted": True}
