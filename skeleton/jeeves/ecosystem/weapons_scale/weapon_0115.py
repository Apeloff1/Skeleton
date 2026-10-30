"""Weapon scale 0115.
"""
from __future__ import annotations

ID = "weapon_scale2_0115"

def describe() -> dict:
    return {"id": ID, "kind": "weapon", "power": 5 + (115 % 25)}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "damage": 8 + (115 % 15)}
