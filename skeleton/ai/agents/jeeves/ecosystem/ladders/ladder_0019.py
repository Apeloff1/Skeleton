"""Ladder 0019.
"""
from __future__ import annotations

LADDER = "ladder_0019"

def climb(direction: int) -> dict:
    return {"ok": True, "ladder": LADDER, "dir": 1 if direction >= 0 else -1}
