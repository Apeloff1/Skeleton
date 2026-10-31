"""Photo preset 0025.
"""
from __future__ import annotations

PRESET = "photo_0025"

def capture(fov: float = 60.0) -> dict:
    return {"ok": True, "preset": PRESET, "fov": fov, "filters": ["none", "warm", "cool"][25 % 3]}
