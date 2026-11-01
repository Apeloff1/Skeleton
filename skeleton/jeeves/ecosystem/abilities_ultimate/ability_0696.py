"""Ability ultimate 0696.
"""
from __future__ import annotations

ID = "ability_ultimate_0696"

def describe() -> dict:
    return {"id": ID, "kind": "ability", "power": 5 + (696 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
