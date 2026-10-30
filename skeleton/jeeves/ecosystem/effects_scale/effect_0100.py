"""Effect scale 0100.
"""
from __future__ import annotations

ID = "effect_scale_0100"

def describe() -> dict:
    return {"id": ID, "kind": "effect", "tier": 100 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
