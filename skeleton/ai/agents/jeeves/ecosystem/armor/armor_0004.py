"""Armor 0004.
"""
from __future__ import annotations

ARMOR = "armor_0004"

def defense() -> int:
    return 5 + (4 % 20)

def equip(slot: str) -> dict:
    if slot not in ("head", "chest", "legs", "feet"):
        return {"ok": False, "reason": "bad_slot"}
    return {"ok": True, "armor": ARMOR, "slot": slot, "def": defense()}
