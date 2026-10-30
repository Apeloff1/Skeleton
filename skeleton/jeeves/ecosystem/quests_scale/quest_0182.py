"""Quest scale 0182.
"""
from __future__ import annotations

ID = "quest_scale_0182"

def describe() -> dict:
    return {"id": ID, "kind": "quest", "tier": 182 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
