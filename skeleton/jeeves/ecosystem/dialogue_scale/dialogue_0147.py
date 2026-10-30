"""Dialogue scale 0147.
"""
from __future__ import annotations

ID = "dialogue_scale_0147"

def describe() -> dict:
    return {"id": ID, "kind": "dialogue", "tier": 147 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
