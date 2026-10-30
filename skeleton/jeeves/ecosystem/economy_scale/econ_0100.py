"""Econ scale 0100.
"""
from __future__ import annotations

ID = "econ_scale_0100"

def describe() -> dict:
    return {"id": ID, "kind": "econ", "value": 10 + 100}

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "id": ID, "player": player, "granted": True}
