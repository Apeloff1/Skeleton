"""Platform 0009.
"""
from __future__ import annotations

PLAT = "plat_0009"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
