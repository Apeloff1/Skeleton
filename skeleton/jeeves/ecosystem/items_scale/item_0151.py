"""Item scale 0151.
"""
from __future__ import annotations

ID = "item_scale_0151"

def describe() -> dict:
    return {"id": ID, "kind": "item", "tier": 151 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
