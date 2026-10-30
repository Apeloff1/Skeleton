"""Explosion scale 0064.
"""
from __future__ import annotations

ID = "explosion_scale2_0064"

def describe() -> dict:
    return {"id": ID, "kind": "explosion", "power": 5 + (64 % 25)}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "damage": 8 + (64 % 15)}
