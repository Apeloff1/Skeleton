"""Platform 0032.
"""
from __future__ import annotations

PLAT = "plat_0032"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
