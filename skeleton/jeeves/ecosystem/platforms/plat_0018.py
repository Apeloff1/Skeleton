"""Platform 0018.
"""
from __future__ import annotations

PLAT = "plat_0018"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
