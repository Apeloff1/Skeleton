"""Ach advanced 0005.
"""
from __future__ import annotations

ID = "ach_adv_0005"

def describe() -> dict:
    return {"id": ID, "kind": "ach", "value": 10 + 5}

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "id": ID, "player": player, "granted": True}
