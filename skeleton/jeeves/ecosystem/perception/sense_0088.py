"""Sense 0088.
"""
from __future__ import annotations

SENSE = "sense_0088"

def detect(noise: float, vision: float) -> dict:
    spotted = vision > 0.5 or noise > 0.7
    return {"ok": True, "sense": SENSE, "spotted": spotted, "alert": vision * 0.6 + noise * 0.4}
