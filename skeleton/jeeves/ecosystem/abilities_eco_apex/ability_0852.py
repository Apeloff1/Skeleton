"""Ability eco_apex 0852.
"""
from __future__ import annotations

ID = "ability_eco_apex_0852"

def describe() -> dict:
    return {"id": ID, "kind": "ability", "power": 5 + (852 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
