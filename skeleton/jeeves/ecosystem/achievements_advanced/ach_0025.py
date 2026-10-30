"""Ach advanced 0025.
"""
from __future__ import annotations

ID = "ach_adv_0025"

def describe() -> dict:
    return {"id": ID, "kind": "ach", "value": 10 + 25}

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "id": ID, "player": player, "granted": True}
