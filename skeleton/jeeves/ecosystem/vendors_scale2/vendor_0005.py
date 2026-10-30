"""Vendor advanced 0005.
"""
from __future__ import annotations

ID = "vendor_adv_0005"

def describe() -> dict:
    return {"id": ID, "kind": "vendor", "value": 10 + 5}

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "id": ID, "player": player, "granted": True}
