"""Explosion scale 0041.
"""
from __future__ import annotations

ID = "explosion_scale2_0041"

def describe() -> dict:
    return {"id": ID, "kind": "explosion", "power": 5 + (41 % 25)}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "damage": 8 + (41 % 15)}
