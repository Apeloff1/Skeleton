"""Rollback 0000.
"""
from __future__ import annotations

ROLL = "roll_0000"

def rewind(frames: int) -> dict:
    frames = max(0, min(16, frames))
    return {"ok": True, "roll": ROLL, "frames": frames}
