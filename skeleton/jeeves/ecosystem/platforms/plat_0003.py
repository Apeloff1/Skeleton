"""Platform 0003.
"""
from __future__ import annotations

PLAT = "plat_0003"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
