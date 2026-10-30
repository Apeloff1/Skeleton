"""Projectile scale 0095.
"""
from __future__ import annotations

ID = "projectile_scale2_0095"

def describe() -> dict:
    return {"id": ID, "kind": "projectile", "power": 5 + (95 % 25)}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "damage": 8 + (95 % 15)}
