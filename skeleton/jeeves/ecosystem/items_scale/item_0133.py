"""Item scale 0133.
"""
from __future__ import annotations

ID = "item_scale_0133"

def describe() -> dict:
    return {"id": ID, "kind": "item", "tier": 133 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
