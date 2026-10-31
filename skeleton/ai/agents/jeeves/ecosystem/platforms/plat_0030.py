"""Platform 0030.
"""
from __future__ import annotations

PLAT = "plat_0030"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
