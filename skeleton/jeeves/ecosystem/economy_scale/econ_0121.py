"""Econ scale 0121.
"""
from __future__ import annotations

ID = "econ_scale_0121"

def describe() -> dict:
    return {"id": ID, "kind": "econ", "value": 10 + 121}

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "id": ID, "player": player, "granted": True}
