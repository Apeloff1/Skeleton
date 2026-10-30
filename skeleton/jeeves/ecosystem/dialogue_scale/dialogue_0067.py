"""Dialogue scale 0067.
"""
from __future__ import annotations

ID = "dialogue_scale_0067"

def describe() -> dict:
    return {"id": ID, "kind": "dialogue", "tier": 67 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
