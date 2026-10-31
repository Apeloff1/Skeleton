"""Platform 0038.
"""
from __future__ import annotations

PLAT = "plat_0038"

def move(delta: float) -> dict:
    return {"ok": True, "plat": PLAT, "delta": delta, "moving": True}
