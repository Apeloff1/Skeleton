"""Photo preset 0008.
"""
from __future__ import annotations

PRESET = "photo_0008"

def capture(fov: float = 60.0) -> dict:
    return {"ok": True, "preset": PRESET, "fov": fov, "filters": ["none", "warm", "cool"][8 % 3]}
