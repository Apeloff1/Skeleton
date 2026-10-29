"""Platform 0010.
"""
from __future__ import annotations

PLAT = "plat_0010"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
