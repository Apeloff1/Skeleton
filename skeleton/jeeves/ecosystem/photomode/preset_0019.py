"""Photo preset 0019.
"""
from __future__ import annotations

PRESET = "photo_0019"

def capture(fov: float = 60.0) -> dict:
    return {"ok": True, "preset": PRESET, "fov": fov, "filters": ["none", "warm", "cool"][19 % 3]}
