"""Armor 0045.
"""
from __future__ import annotations

ARMOR = "armor_0045"

def defense() -> int:
    return 5 + (45 % 20)

def equip(slot: str) -> dict:
    if slot not in ("head", "chest", "legs", "feet"):
        return {"ok": False, "reason": "bad_slot"}
    return {"ok": True, "armor": ARMOR, "slot": slot, "def": defense()}
