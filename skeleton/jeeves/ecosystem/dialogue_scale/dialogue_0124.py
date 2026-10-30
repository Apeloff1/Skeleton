"""Dialogue scale 0124.
"""
from __future__ import annotations

ID = "dialogue_scale_0124"

def describe() -> dict:
    return {"id": ID, "kind": "dialogue", "tier": 124 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
