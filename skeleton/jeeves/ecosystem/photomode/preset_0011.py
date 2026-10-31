"""Photo preset 0011.
"""
from __future__ import annotations

PRESET = "photo_0011"

def capture(fov: float = 60.0) -> dict:
    return {"ok": True, "preset": PRESET, "fov": fov, "filters": ["none", "warm", "cool"][11 % 3]}
