"""Ammo scale 0016.
"""
from __future__ import annotations

ID = "ammo_scale2_0016"

def describe() -> dict:
    return {"id": ID, "kind": "ammo", "power": 5 + (16 % 25)}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "damage": 8 + (16 % 15)}
