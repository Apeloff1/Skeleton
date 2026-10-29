"""Platform 0025.
"""
from __future__ import annotations

PLAT = "plat_0025"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
