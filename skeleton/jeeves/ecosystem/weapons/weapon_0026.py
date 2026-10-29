"""Weapon 0026.
"""
from __future__ import annotations

WEAPON = "weapon_0026"

def damage() -> int:
    return 8 + (26 % 25)

def swing(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "weapon": WEAPON, "target": target, "damage": damage()}
