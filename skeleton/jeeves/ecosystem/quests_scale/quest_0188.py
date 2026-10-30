"""Quest scale 0188.
"""
from __future__ import annotations

ID = "quest_scale_0188"

def describe() -> dict:
    return {"id": ID, "kind": "quest", "tier": 188 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
