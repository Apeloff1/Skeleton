"""Joint 0011.
"""
from __future__ import annotations

JOINT = "joint_0011"

def connect(a: str, b: str) -> dict:
    if not a or not b:
        return {"ok": False, "reason": "missing"}
    return {"ok": True, "joint": JOINT, "a": a, "b": b}
