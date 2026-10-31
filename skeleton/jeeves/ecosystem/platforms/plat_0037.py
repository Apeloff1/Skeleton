"""Platform 0037.
"""
from __future__ import annotations

PLAT = "plat_0037"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
