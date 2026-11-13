"""Photo preset 0024.
"""
from __future__ import annotations

PRESET = "photo_0024"

def capture(fov: float = 60.0) -> dict:
    return {"ok": True, "preset": PRESET, "fov": fov, "filters": ["none", "warm", "cool"][24 % 3]}
