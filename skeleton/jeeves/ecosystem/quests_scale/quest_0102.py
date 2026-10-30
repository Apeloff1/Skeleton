"""Quest scale 0102.
"""
from __future__ import annotations

ID = "quest_scale_0102"

def describe() -> dict:
    return {"id": ID, "kind": "quest", "tier": 102 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
