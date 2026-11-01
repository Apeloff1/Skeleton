"""Skill ultimate 0454.
"""
from __future__ import annotations

ID = "skill_ultimate_0454"

def describe() -> dict:
    return {"id": ID, "kind": "skill", "power": 5 + (454 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
