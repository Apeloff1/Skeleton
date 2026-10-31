"""Respawn 0016.
"""
from __future__ import annotations

POINT = "respawn_0016"

def bind(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "point": POINT, "player": player}
