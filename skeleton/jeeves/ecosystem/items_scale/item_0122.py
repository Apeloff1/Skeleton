"""Item scale 0122.
"""
from __future__ import annotations

ID = "item_scale_0122"

def describe() -> dict:
    return {"id": ID, "kind": "item", "tier": 122 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
