"""Decal 0008.
"""
from __future__ import annotations

DECAL = "decal_0008"

def place(surface: str) -> dict:
    if not surface:
        return {"ok": False, "reason": "no_surface"}
    return {"ok": True, "decal": DECAL, "surface": surface}
