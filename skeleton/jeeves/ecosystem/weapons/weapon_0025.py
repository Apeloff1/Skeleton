"""Weapon 0025.
"""
from __future__ import annotations

WEAPON = "weapon_0025"

def damage() -> int:
    return 8 + (25 % 25)

def swing(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "weapon": WEAPON, "target": target, "damage": damage()}
