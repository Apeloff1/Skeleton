"""Dialogue scale 0127.
"""
from __future__ import annotations

ID = "dialogue_scale_0127"

def describe() -> dict:
    return {"id": ID, "kind": "dialogue", "tier": 127 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
