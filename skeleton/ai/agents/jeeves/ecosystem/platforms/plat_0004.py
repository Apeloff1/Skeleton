"""Platform 0004.
"""
from __future__ import annotations

PLAT = "plat_0004"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
