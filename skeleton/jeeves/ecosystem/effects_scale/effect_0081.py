"""Effect scale 0081.
"""
from __future__ import annotations

ID = "effect_scale_0081"

def describe() -> dict:
    return {"id": ID, "kind": "effect", "tier": 81 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
