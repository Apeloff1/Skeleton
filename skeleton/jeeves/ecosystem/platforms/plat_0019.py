"""Platform 0019.
"""
from __future__ import annotations

PLAT = "plat_0019"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
