"""Platform 0011.
"""
from __future__ import annotations

PLAT = "plat_0011"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
