"""Ability scale 0170.
"""
from __future__ import annotations

ID = "ability_scale_0170"

def describe() -> dict:
    return {"id": ID, "kind": "ability", "power": 5 + (170 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
