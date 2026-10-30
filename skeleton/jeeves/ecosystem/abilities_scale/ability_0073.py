"""Ability scale 0073.
"""
from __future__ import annotations

ID = "ability_scale_0073"

def describe() -> dict:
    return {"id": ID, "kind": "ability", "tier": 73 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
