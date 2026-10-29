"""Status effect: poison.
"""
from __future__ import annotations

NAME = "poison"
DURATION = 3.0

def apply(target: str, stacks: int = 1) -> dict:
    if not target or stacks < 1:
        return {"ok": False, "reason": "bad_target"}
    return {"ok": True, "effect": NAME, "target": target, "stacks": min(stacks, 5), "duration": DURATION}

def tick(remaining: float) -> dict:
    return {"ok": True, "effect": NAME, "remaining": max(0.0, remaining - 1.0)}
