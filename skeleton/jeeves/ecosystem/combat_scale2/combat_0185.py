"""Combat scale 0185.
"""
from __future__ import annotations

ID = "combat_scale2_0185"

def describe() -> dict:
    return {"id": ID, "kind": "combat", "power": 5 + (185 % 25)}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "damage": 8 + (185 % 15)}
