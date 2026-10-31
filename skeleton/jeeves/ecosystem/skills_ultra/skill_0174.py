"""Skill ultra 0174.
"""
from __future__ import annotations

ID = "skill_ultra_0174"

def describe() -> dict:
    return {"id": ID, "kind": "skill", "power": 5 + (174 % 20)}

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "id": ID, "target": target, "stacks": min(5, stacks)}
