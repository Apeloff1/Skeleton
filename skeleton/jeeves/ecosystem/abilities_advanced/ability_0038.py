"""Ability scale 0038.
"""
from __future__ import annotations

ID = "ability_scale_0038"

def describe() -> dict:
    return {"id": ID, "kind": "ability", "power": 5 + (38 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
