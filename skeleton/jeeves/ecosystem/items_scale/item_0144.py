"""Item scale 0144.
"""
from __future__ import annotations

ID = "item_scale_0144"

def describe() -> dict:
    return {"id": ID, "kind": "item", "tier": 144 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
