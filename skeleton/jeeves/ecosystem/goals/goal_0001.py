"""Goal 0001.
"""
from __future__ import annotations

GOAL = "goal_0001"

def progress(current: int, target: int = 1) -> dict:
    target = max(1, target)
    return {"ok": True, "goal": GOAL, "current": current, "target": target, "done": current >= target}
