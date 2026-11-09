"""Platform 0020.
"""
from __future__ import annotations

PLAT = "plat_0020"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
