"""Weapon 0003.
"""
from __future__ import annotations

WEAPON = "weapon_0003"

def damage() -> int:
    return 8 + (3 % 25)

def swing(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "weapon": WEAPON, "target": target, "damage": damage()}
