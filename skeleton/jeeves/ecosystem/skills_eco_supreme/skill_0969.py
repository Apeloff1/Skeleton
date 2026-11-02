"""Skill eco_supreme 0969.
"""
from __future__ import annotations

ID = "skill_eco_supreme_0969"

def describe() -> dict:
    return {"id": ID, "kind": "skill", "power": 5 + (969 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
