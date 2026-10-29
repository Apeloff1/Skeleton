"""Rollback 0011.
"""
from __future__ import annotations

ROLL = "roll_0011"

def rewind(frames: int) -> dict:
    frames = max(0, min(16, frames))
    return {"ok": True, "roll": ROLL, "frames": frames}
