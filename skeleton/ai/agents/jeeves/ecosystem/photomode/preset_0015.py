"""Photo preset 0015.
"""
from __future__ import annotations

PRESET = "photo_0015"

def capture(fov: float = 60.0) -> dict:
    return {"ok": True, "preset": PRESET, "fov": fov, "filters": ["none", "warm", "cool"][15 % 3]}
