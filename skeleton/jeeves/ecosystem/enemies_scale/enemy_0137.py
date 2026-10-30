"""Enemy scale 0137.
"""
from __future__ import annotations

ID = "enemy_scale_0137"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "tier": 137 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
