"""Dialogue scale 0060.
"""
from __future__ import annotations

ID = "dialogue_scale_0060"

def describe() -> dict:
    return {"id": ID, "kind": "dialogue", "tier": 60 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
