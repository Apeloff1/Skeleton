"""Platform 0022.
"""
from __future__ import annotations

PLAT = "plat_0022"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
