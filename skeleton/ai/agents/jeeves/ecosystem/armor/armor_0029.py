"""Armor 0029.
"""
from __future__ import annotations

ARMOR = "armor_0029"

def defense() -> int:
    return 5 + (29 % 20)

def equip(slot: str) -> dict:
    if slot not in ("head", "chest", "legs", "feet"):
        return {"ok": False, "reason": "bad_slot"}
    return {"ok": True, "armor": ARMOR, "slot": slot, "def": defense()}
