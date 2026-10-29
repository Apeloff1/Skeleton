"""Debuff 0036.
"""
from __future__ import annotations

DEBUFF = "debuff_0036"

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "debuff": DEBUFF, "target": target, "stacks": min(5, stacks), "penalty": 0.05 * stacks}
