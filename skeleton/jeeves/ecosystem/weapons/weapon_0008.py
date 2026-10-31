"""Weapon 0008.
"""
from __future__ import annotations

WEAPON = "weapon_0008"

def damage() -> int:
    return 8 + (8 % 25)

def swing(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "weapon": WEAPON, "target": target, "damage": damage()}
