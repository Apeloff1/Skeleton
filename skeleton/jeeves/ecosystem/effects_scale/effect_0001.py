"""Effect scale 0001.
"""
from __future__ import annotations

ID = "effect_scale_0001"

def describe() -> dict:
    return {"id": ID, "kind": "effect", "tier": 1 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
