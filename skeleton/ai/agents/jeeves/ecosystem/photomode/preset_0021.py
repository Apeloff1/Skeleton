"""Photo preset 0021.
"""
from __future__ import annotations

PRESET = "photo_0021"

def capture(fov: float = 60.0) -> dict:
    return {"ok": True, "preset": PRESET, "fov": fov, "filters": ["none", "warm", "cool"][21 % 3]}
