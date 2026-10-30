"""Combat scale 0159.
"""
from __future__ import annotations

ID = "combat_scale2_0159"

def describe() -> dict:
    return {"id": ID, "kind": "combat", "power": 5 + (159 % 25)}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "damage": 8 + (159 % 15)}
