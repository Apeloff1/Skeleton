"""Quest scale 0180.
"""
from __future__ import annotations

ID = "quest_scale_0180"

def describe() -> dict:
    return {"id": ID, "kind": "quest", "tier": 180 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
