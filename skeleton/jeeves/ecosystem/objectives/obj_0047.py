"""Objective 0047.
"""
from __future__ import annotations

OBJ = "obj_0047"

def progress(current: int, target: int = 1) -> dict:
    target = max(1, target)
    done = current >= target
    return {"ok": True, "obj": OBJ, "current": current, "target": target, "done": done}
