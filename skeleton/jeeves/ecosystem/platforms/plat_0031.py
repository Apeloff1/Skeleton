"""Platform 0031.
"""
from __future__ import annotations

PLAT = "plat_0031"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
