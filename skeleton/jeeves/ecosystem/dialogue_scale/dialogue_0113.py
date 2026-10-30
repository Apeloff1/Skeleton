"""Dialogue scale 0113.
"""
from __future__ import annotations

ID = "dialogue_scale_0113"

def describe() -> dict:
    return {"id": ID, "kind": "dialogue", "tier": 113 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
