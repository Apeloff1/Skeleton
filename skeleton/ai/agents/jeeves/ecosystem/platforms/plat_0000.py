"""Platform 0000.
"""
from __future__ import annotations

PLAT = "plat_0000"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
