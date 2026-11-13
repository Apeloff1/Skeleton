"""Checkpoint 014.
"""
from __future__ import annotations

FLAG = "flag_014"

def activate(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "flag": FLAG, "player": player, "respawn": True}
