"""Platform 0007.
"""
from __future__ import annotations

PLAT = "plat_0007"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
