"""Econ advanced 0079.
"""
from __future__ import annotations

ID = "econ_adv_0079"

def describe() -> dict:
    return {"id": ID, "kind": "econ", "value": 10 + 79}

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "id": ID, "player": player, "granted": True}
