"""Armor scale 0105.
"""
from __future__ import annotations

ID = "armor_scale2_0105"

def describe() -> dict:
    return {"id": ID, "kind": "armor", "power": 5 + (105 % 25)}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "damage": 8 + (105 % 15)}
