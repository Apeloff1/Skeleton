"""Joint 0044.
"""
from __future__ import annotations

JOINT = "joint_0044"

def connect(a: str, b: str) -> dict:
    if not a or not b:
        return {"ok": False, "reason": "missing"}
    return {"ok": True, "joint": JOINT, "a": a, "b": b}
