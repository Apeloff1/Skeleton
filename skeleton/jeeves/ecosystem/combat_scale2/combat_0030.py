"""Combat scale 0030.
"""
from __future__ import annotations

ID = "combat_scale2_0030"

def describe() -> dict:
    return {"id": ID, "kind": "combat", "power": 5 + (30 % 25)}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "damage": 8 + (30 % 15)}
