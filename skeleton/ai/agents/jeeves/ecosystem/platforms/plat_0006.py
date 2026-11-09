"""Platform 0006.
"""
from __future__ import annotations

PLAT = "plat_0006"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
