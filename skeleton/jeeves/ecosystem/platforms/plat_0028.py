"""Platform 0028.
"""
from __future__ import annotations

PLAT = "plat_0028"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
