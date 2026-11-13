"""Weapon 0051.
"""
from __future__ import annotations

WEAPON = "weapon_0051"

def damage() -> int:
    return 8 + (51 % 25)

def swing(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "weapon": WEAPON, "target": target, "damage": damage()}
