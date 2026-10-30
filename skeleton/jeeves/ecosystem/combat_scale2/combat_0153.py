"""Combat scale 0153.
"""
from __future__ import annotations

ID = "combat_scale2_0153"

def describe() -> dict:
    return {"id": ID, "kind": "combat", "power": 5 + (153 % 25)}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "damage": 8 + (153 % 15)}
