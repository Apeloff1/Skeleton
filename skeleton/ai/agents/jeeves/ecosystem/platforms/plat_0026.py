"""Platform 0026.
"""
from __future__ import annotations

PLAT = "plat_0026"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
