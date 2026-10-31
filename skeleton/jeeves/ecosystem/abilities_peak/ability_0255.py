"""Ability peak 0255.
"""
from __future__ import annotations

ID = "ability_peak_0255"

def describe() -> dict:
    return {"id": ID, "kind": "ability", "power": 5 + (255 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
