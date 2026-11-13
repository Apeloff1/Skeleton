"""Buff 0094.
"""
from __future__ import annotations

BUFF = "buff_0094"

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad"}
    return {"ok": True, "buff": BUFF, "target": target, "stacks": min(5, stacks), "bonus": 0.05 * stacks}
