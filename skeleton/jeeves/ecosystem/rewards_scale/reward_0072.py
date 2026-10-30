"""Reward scale 0072.
"""
from __future__ import annotations

ID = "reward_scale_0072"

def describe() -> dict:
    return {"id": ID, "kind": "reward", "tier": 72 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
