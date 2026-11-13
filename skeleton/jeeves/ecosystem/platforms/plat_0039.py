"""Platform 0039.
"""
from __future__ import annotations

PLAT = "plat_0039"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
