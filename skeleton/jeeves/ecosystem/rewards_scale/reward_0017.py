"""Reward scale 0017.
"""
from __future__ import annotations

ID = "reward_scale_0017"

def describe() -> dict:
    return {"id": ID, "kind": "reward", "tier": 17 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
