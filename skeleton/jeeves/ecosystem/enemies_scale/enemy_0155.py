"""Enemy scale 0155.
"""
from __future__ import annotations

ID = "enemy_scale_0155"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "tier": 155 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
