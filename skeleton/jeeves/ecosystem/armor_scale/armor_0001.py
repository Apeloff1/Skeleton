"""Armor scale 0001.
"""
from __future__ import annotations

ID = "armor_scale2_0001"

def describe() -> dict:
    return {"id": ID, "kind": "armor", "power": 5 + (1 % 25)}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "damage": 8 + (1 % 15)}
