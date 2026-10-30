"""Ach advanced 0055.
"""
from __future__ import annotations

ID = "ach_adv_0055"

def describe() -> dict:
    return {"id": ID, "kind": "ach", "value": 10 + 55}

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "id": ID, "player": player, "granted": True}
