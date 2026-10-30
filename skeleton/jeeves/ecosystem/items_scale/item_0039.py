"""Item scale 0039.
"""
from __future__ import annotations

ID = "item_scale_0039"

def describe() -> dict:
    return {"id": ID, "kind": "item", "tier": 39 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
