"""Ability ultimate 0636.
"""
from __future__ import annotations

ID = "ability_ultimate_0636"

def describe() -> dict:
    return {"id": ID, "kind": "ability", "power": 5 + (636 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
