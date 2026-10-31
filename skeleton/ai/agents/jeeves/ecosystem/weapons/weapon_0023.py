"""Weapon 0023.
"""
from __future__ import annotations

WEAPON = "weapon_0023"

def damage() -> int:
    return 8 + (23 % 25)

def swing(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "weapon": WEAPON, "target": target, "damage": damage()}
