"""Armor 0016.
"""
from __future__ import annotations

ARMOR = "armor_0016"

def defense() -> int:
    return 5 + (16 % 20)

def equip(slot: str) -> dict:
    if slot not in ("head", "chest", "legs", "feet"):
        return {"ok": False, "reason": "bad_slot"}
    return {"ok": True, "armor": ARMOR, "slot": slot, "def": defense()}
