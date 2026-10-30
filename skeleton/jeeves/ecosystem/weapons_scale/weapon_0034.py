"""Weapon scale 0034.
"""
from __future__ import annotations

ID = "weapon_scale2_0034"

def describe() -> dict:
    return {"id": ID, "kind": "weapon", "power": 5 + (34 % 25)}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "damage": 8 + (34 % 15)}
