"""Platform 0012.
"""
from __future__ import annotations

PLAT = "plat_0012"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
