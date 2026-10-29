"""Armor 0044.
"""
from __future__ import annotations

ARMOR = "armor_0044"

def defense() -> int:
    return 5 + (44 % 20)

def equip(slot: str) -> dict:
    if slot not in ("head", "chest", "legs", "feet"):
        return {"ok": False, "reason": "bad_slot"}
    return {"ok": True, "armor": ARMOR, "slot": slot, "def": defense()}
