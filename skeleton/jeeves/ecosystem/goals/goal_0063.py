"""Goal 0063.
"""
from __future__ import annotations

GOAL = "goal_0063"

def progress(current: int, target: int = 1) -> dict:
    target = max(1, target)
    return {"ok": True, "goal": GOAL, "current": current, "target": target, "done": current >= target}
