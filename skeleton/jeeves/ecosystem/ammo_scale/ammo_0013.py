"""Ammo scale 0013.
"""
from __future__ import annotations

ID = "ammo_scale2_0013"

def describe() -> dict:
    return {"id": ID, "kind": "ammo", "power": 5 + (13 % 25)}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "damage": 8 + (13 % 15)}
