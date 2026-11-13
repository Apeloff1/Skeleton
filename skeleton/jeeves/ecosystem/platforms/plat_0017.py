"""Platform 0017.
"""
from __future__ import annotations

PLAT = "plat_0017"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
