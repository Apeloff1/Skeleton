"""Armor scale 0112.
"""
from __future__ import annotations

ID = "armor_scale2_0112"

def describe() -> dict:
    return {"id": ID, "kind": "armor", "power": 5 + (112 % 25)}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "damage": 8 + (112 % 15)}
