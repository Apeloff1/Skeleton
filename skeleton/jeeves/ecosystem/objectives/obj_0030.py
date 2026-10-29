"""Objective 0030.
"""
from __future__ import annotations

OBJ = "obj_0030"

def progress(current: int, target: int = 1) -> dict:
    target = max(1, target)
    done = current >= target
    return {"ok": True, "obj": OBJ, "current": current, "target": target, "done": done}
