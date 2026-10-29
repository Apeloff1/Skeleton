"""Destructible 0029.
"""
from __future__ import annotations

DEST = "dest_0029"

def hit(hp: int, dmg: int) -> dict:
    left = max(0, hp - dmg)
    return {"ok": True, "dest": DEST, "hp": left, "broken": left == 0}
