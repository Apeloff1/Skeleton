"""Goal 0061.
"""
from __future__ import annotations

GOAL = "goal_0061"

def progress(current: int, target: int = 1) -> dict:
    target = max(1, target)
    return {"ok": True, "goal": GOAL, "current": current, "target": target, "done": current >= target}
