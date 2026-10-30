"""Vendor scale 0026.
"""
from __future__ import annotations

ID = "vendor_scale_0026"

def describe() -> dict:
    return {"id": ID, "kind": "vendor", "value": 10 + 26}

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "id": ID, "player": player, "granted": True}
