"""Econ advanced 0132.
"""
from __future__ import annotations

ID = "econ_adv_0132"

def describe() -> dict:
    return {"id": ID, "kind": "econ", "value": 10 + 132}

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "id": ID, "player": player, "granted": True}
