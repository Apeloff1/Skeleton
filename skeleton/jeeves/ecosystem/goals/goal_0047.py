"""Goal 0047.
"""
from __future__ import annotations

GOAL = "goal_0047"

def progress(current: int, target: int = 1) -> dict:
    target = max(1, target)
    return {"ok": True, "goal": GOAL, "current": current, "target": target, "done": current >= target}
