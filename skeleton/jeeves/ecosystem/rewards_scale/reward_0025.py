"""Reward scale 0025.
"""
from __future__ import annotations

ID = "reward_scale_0025"

def describe() -> dict:
    return {"id": ID, "kind": "reward", "tier": 25 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
