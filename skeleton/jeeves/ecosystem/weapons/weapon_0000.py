"""Weapon 0000.
"""
from __future__ import annotations

WEAPON = "weapon_0000"

def damage() -> int:
    return 8 + (0 % 25)

def swing(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "weapon": WEAPON, "target": target, "damage": damage()}
