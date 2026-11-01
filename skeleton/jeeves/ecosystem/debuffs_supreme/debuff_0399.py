"""Debuff supreme 0399.
"""
from __future__ import annotations

ID = "debuff_supreme_0399"

def describe() -> dict:
    return {"id": ID, "kind": "debuff", "power": 5 + (399 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
