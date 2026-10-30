"""Ability scale 0117.
"""
from __future__ import annotations

ID = "ability_scale_0117"

def describe() -> dict:
    return {"id": ID, "kind": "ability", "tier": 117 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
