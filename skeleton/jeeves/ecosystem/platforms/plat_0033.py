"""Platform 0033.
"""
from __future__ import annotations

PLAT = "plat_0033"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
