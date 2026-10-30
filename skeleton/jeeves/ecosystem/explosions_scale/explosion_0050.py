"""Explosion scale 0050.
"""
from __future__ import annotations

ID = "explosion_scale2_0050"

def describe() -> dict:
    return {"id": ID, "kind": "explosion", "power": 5 + (50 % 25)}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "damage": 8 + (50 % 15)}
