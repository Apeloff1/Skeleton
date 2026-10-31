"""Photo preset 0000.
"""
from __future__ import annotations

PRESET = "photo_0000"

def capture(fov: float = 60.0) -> dict:
    return {"ok": True, "preset": PRESET, "fov": fov, "filters": ["none", "warm", "cool"][0 % 3]}
