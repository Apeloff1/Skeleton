"""Platform 0015.
"""
from __future__ import annotations

PLAT = "plat_0015"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
