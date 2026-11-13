"""Platform 0001.
"""
from __future__ import annotations

PLAT = "plat_0001"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
