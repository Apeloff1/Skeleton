"""Weapon 0053.
"""
from __future__ import annotations

WEAPON = "weapon_0053"

def damage() -> int:
    return 8 + (53 % 25)

def swing(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "weapon": WEAPON, "target": target, "damage": damage()}
