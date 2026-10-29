"""Platform 0021.
"""
from __future__ import annotations

PLAT = "plat_0021"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
