"""Weapon scale 0137.
"""
from __future__ import annotations

ID = "weapon_scale2_0137"

def describe() -> dict:
    return {"id": ID, "kind": "weapon", "power": 5 + (137 % 25)}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "damage": 8 + (137 % 15)}
