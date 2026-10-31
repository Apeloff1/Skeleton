"""Photo preset 0027.
"""
from __future__ import annotations

PRESET = "photo_0027"

def capture(fov: float = 60.0) -> dict:
    return {"ok": True, "preset": PRESET, "fov": fov, "filters": ["none", "warm", "cool"][27 % 3]}
