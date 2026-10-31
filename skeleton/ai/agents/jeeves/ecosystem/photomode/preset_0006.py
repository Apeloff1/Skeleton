"""Photo preset 0006.
"""
from __future__ import annotations

PRESET = "photo_0006"

def capture(fov: float = 60.0) -> dict:
    return {"ok": True, "preset": PRESET, "fov": fov, "filters": ["none", "warm", "cool"][6 % 3]}
