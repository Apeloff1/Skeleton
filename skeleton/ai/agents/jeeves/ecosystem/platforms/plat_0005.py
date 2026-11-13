"""Platform 0005.
"""
from __future__ import annotations

PLAT = "plat_0005"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
