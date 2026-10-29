"""Platform 0027.
"""
from __future__ import annotations

PLAT = "plat_0027"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
