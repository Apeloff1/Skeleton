"""Checkpoint 005.
"""
from __future__ import annotations

FLAG = "flag_005"

def activate(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "flag": FLAG, "player": player, "respawn": True}
