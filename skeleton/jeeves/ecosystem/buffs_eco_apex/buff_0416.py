"""Buff eco_apex 0416.
"""
from __future__ import annotations

ID = "buff_eco_apex_0416"

def describe() -> dict:
    return {"id": ID, "kind": "buff", "power": 5 + (416 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
