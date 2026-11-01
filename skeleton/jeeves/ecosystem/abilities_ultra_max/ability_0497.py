"""Ability ultra_max 0497.
"""
from __future__ import annotations

ID = "ability_ultra_max_0497"

def describe() -> dict:
    return {"id": ID, "kind": "ability", "power": 5 + (497 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
