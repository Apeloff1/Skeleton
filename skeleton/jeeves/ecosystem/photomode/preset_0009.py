"""Photo preset 0009.
"""
from __future__ import annotations

PRESET = "photo_0009"

def capture(fov: float = 60.0) -> dict:
    return {"ok": True, "preset": PRESET, "fov": fov, "filters": ["none", "warm", "cool"][9 % 3]}
