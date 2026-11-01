"""Ability ultra_max 0431.
"""
from __future__ import annotations

ID = "ability_ultra_max_0431"

def describe() -> dict:
    return {"id": ID, "kind": "ability", "power": 5 + (431 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
