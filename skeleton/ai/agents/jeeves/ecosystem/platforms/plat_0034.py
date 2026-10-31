"""Platform 0034.
"""
from __future__ import annotations

PLAT = "plat_0034"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
