"""Platform 0002.
"""
from __future__ import annotations

PLAT = "plat_0002"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
