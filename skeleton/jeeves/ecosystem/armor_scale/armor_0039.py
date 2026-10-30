"""Armor scale 0039.
"""
from __future__ import annotations

ID = "armor_scale2_0039"

def describe() -> dict:
    return {"id": ID, "kind": "armor", "power": 5 + (39 % 25)}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "damage": 8 + (39 % 15)}
