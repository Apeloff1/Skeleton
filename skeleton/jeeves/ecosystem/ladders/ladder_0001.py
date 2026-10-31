"""Ladder 0001.
"""
from __future__ import annotations

LADDER = "ladder_0001"

def climb(direction: int) -> dict:
    return {"ok": True, "ladder": LADDER, "dir": 1 if direction >= 0 else -1}
