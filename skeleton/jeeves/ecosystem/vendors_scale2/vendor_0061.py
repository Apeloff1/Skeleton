"""Vendor advanced 0061.
"""
from __future__ import annotations

ID = "vendor_adv_0061"

def describe() -> dict:
    return {"id": ID, "kind": "vendor", "value": 10 + 61}

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "id": ID, "player": player, "granted": True}
