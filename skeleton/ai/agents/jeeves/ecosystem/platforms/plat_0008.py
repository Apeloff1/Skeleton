"""Platform 0008.
"""
from __future__ import annotations

PLAT = "plat_0008"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
