"""Combat scale 0156.
"""
from __future__ import annotations

ID = "combat_scale2_0156"

def describe() -> dict:
    return {"id": ID, "kind": "combat", "power": 5 + (156 % 25)}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "damage": 8 + (156 % 15)}
