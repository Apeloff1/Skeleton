"""Platform 0024.
"""
from __future__ import annotations

PLAT = "plat_0024"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
