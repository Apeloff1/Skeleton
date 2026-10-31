"""Platform 0036.
"""
from __future__ import annotations

PLAT = "plat_0036"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
