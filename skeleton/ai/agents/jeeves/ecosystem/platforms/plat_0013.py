"""Platform 0013.
"""
from __future__ import annotations

PLAT = "plat_0013"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
