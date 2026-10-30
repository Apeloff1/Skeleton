"""Vendor advanced 0082.
"""
from __future__ import annotations

ID = "vendor_adv_0082"

def describe() -> dict:
    return {"id": ID, "kind": "vendor", "value": 10 + 82}

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "id": ID, "player": player, "granted": True}
