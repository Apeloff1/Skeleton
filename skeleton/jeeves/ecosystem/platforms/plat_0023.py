"""Platform 0023.
"""
from __future__ import annotations

PLAT = "plat_0023"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
