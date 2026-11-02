"""Skill eco_apex 0357.
"""
from __future__ import annotations

ID = "skill_eco_apex_0357"

def describe() -> dict:
    return {"id": ID, "kind": "skill", "power": 5 + (357 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
