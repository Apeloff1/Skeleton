"""Destructible 0028.
"""
from __future__ import annotations

DEST = "dest_0028"

def hit(hp: int, dmg: int) -> dict:
    left = max(0, hp - dmg)
    return {"ok": True, "dest": DEST, "hp": left, "broken": left == 0}
