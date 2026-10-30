"""Item scale 0027.
"""
from __future__ import annotations

ID = "item_scale_0027"

def describe() -> dict:
    return {"id": ID, "kind": "item", "tier": 27 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
