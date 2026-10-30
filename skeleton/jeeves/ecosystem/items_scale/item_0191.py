"""Item scale 0191.
"""
from __future__ import annotations

ID = "item_scale_0191"

def describe() -> dict:
    return {"id": ID, "kind": "item", "tier": 191 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
