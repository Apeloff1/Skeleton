"""Projectile scale 0049.
"""
from __future__ import annotations

ID = "projectile_scale2_0049"

def describe() -> dict:
    return {"id": ID, "kind": "projectile", "power": 5 + (49 % 25)}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "damage": 8 + (49 % 15)}
