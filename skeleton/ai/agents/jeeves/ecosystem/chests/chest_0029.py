"""Chest 0029.
"""
from __future__ import annotations

CHEST = "chest_0029"

def open_chest(has_key: bool) -> dict:
    if not has_key:
        return {"ok": False, "reason": "locked"}
    return {"ok": True, "chest": CHEST, "loot": f"loot_{29}"}
