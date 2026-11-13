"""Stealth zone 0022.
"""
from __future__ import annotations

ZONE = "stealth_0022"

def detect(noise: float) -> dict:
    spotted = noise > 0.6
    return {"ok": True, "zone": ZONE, "spotted": spotted, "noise": noise}
