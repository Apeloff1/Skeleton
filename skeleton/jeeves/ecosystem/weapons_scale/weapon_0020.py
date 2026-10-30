"""Weapon scale 0020.
"""
from __future__ import annotations

ID = "weapon_scale2_0020"

def describe() -> dict:
    return {"id": ID, "kind": "weapon", "power": 5 + (20 % 25)}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "damage": 8 + (20 % 15)}
