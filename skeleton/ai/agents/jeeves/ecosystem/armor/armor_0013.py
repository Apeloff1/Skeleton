"""Armor 0013.
"""
from __future__ import annotations

ARMOR = "armor_0013"

def defense() -> int:
    return 5 + (13 % 20)

def equip(slot: str) -> dict:
    if slot not in ("head", "chest", "legs", "feet"):
        return {"ok": False, "reason": "bad_slot"}
    return {"ok": True, "armor": ARMOR, "slot": slot, "def": defense()}
