"""Buff ultra 0001.
"""
from __future__ import annotations

ID = "buff_ultra_0001"

def describe() -> dict:
    return {"id": ID, "kind": "buff", "power": 5 + (1 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
