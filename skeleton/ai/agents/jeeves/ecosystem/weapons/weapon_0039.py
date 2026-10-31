"""Weapon 0039.
"""
from __future__ import annotations

WEAPON = "weapon_0039"

def damage() -> int:
    return 8 + (39 % 25)

def swing(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "weapon": WEAPON, "target": target, "damage": damage()}
