"""Reward scale 0096.
"""
from __future__ import annotations

ID = "reward_scale_0096"

def describe() -> dict:
    return {"id": ID, "kind": "reward", "tier": 96 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
