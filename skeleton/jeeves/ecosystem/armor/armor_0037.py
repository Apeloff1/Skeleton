"""Armor 0037.
"""
from __future__ import annotations

ARMOR = "armor_0037"

def defense() -> int:
    return 5 + (37 % 20)

def equip(slot: str) -> dict:
    if slot not in ("head", "chest", "legs", "feet"):
        return {"ok": False, "reason": "bad_slot"}
    return {"ok": True, "armor": ARMOR, "slot": slot, "def": defense()}
