"""Quest scale 0174.
"""
from __future__ import annotations

ID = "quest_scale_0174"

def describe() -> dict:
    return {"id": ID, "kind": "quest", "tier": 174 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
