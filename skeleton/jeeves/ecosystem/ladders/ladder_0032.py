"""Ladder 0032.
"""
from __future__ import annotations

LADDER = "ladder_0032"

def climb(direction: int) -> dict:
    return {"ok": True, "ladder": LADDER, "dir": 1 if direction >= 0 else -1}
