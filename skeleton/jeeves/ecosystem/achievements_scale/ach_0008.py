"""Ach scale 0008.
"""
from __future__ import annotations

ID = "ach_scale_0008"

def describe() -> dict:
    return {"id": ID, "kind": "ach", "value": 10 + 8}

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "id": ID, "player": player, "granted": True}
