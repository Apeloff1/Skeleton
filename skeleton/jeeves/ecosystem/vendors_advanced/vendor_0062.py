"""Vendor scale 0062.
"""
from __future__ import annotations

ID = "vendor_scale_0062"

def describe() -> dict:
    return {"id": ID, "kind": "vendor", "value": 10 + 62}

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "id": ID, "player": player, "granted": True}
