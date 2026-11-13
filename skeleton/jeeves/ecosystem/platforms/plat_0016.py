"""Platform 0016.
"""
from __future__ import annotations

PLAT = "plat_0016"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
