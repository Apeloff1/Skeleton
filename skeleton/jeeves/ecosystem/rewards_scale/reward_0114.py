"""Reward scale 0114.
"""
from __future__ import annotations

ID = "reward_scale_0114"

def describe() -> dict:
    return {"id": ID, "kind": "reward", "tier": 114 % 5}

def apply(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "id": ID, "target": target, "applied": True}
