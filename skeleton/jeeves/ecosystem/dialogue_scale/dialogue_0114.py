"""Dialogue scale 0114.
"""
from __future__ import annotations

ID = "dialogue_scale_0114"

def describe() -> dict:
    return {"id": ID, "kind": "dialogue", "tier": 114 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
