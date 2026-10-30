"""Ach advanced 0098.
"""
from __future__ import annotations

ID = "ach_adv_0098"

def describe() -> dict:
    return {"id": ID, "kind": "ach", "value": 10 + 98}

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "id": ID, "player": player, "granted": True}
