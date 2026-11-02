"""Debuff eco_supreme 0233.
"""
from __future__ import annotations

ID = "debuff_eco_supreme_0233"

def describe() -> dict:
    return {"id": ID, "kind": "debuff", "power": 5 + (233 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
