"""Photo preset 0028.
"""
from __future__ import annotations

PRESET = "photo_0028"

def capture(fov: float = 60.0) -> dict:
    return {"ok": True, "preset": PRESET, "fov": fov, "filters": ["none", "warm", "cool"][28 % 3]}
