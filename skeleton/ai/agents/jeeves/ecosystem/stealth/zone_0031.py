"""Stealth zone 0031.
"""
from __future__ import annotations

ZONE = "stealth_0031"

def detect(noise: float) -> dict:
    spotted = noise > 0.6
    return {"ok": True, "zone": ZONE, "spotted": spotted, "noise": noise}
