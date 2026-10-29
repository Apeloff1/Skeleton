"""Weapon 0018.
"""
from __future__ import annotations

WEAPON = "weapon_0018"

def damage() -> int:
    return 8 + (18 % 25)

def swing(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "weapon": WEAPON, "target": target, "damage": damage()}
