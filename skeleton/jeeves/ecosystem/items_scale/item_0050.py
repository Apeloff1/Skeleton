"""Item scale 0050.
"""
from __future__ import annotations

ID = "item_scale_0050"

def describe() -> dict:
    return {"id": ID, "kind": "item", "tier": 50 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
