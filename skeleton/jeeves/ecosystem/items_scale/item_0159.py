"""Item scale 0159.
"""
from __future__ import annotations

ID = "item_scale_0159"

def describe() -> dict:
    return {"id": ID, "kind": "item", "tier": 159 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
