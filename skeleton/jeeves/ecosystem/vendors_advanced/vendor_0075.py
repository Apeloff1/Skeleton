"""Vendor scale 0075.
"""
from __future__ import annotations

ID = "vendor_scale_0075"

def describe() -> dict:
    return {"id": ID, "kind": "vendor", "value": 10 + 75}

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "id": ID, "player": player, "granted": True}
