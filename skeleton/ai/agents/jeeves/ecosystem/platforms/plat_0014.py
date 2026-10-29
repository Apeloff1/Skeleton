"""Platform 0014.
"""
from __future__ import annotations

PLAT = "plat_0014"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
