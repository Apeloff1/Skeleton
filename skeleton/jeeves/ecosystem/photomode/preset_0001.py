"""Photo preset 0001.
"""
from __future__ import annotations

PRESET = "photo_0001"

def capture(fov: float = 60.0) -> dict:
    return {"ok": True, "preset": PRESET, "fov": fov, "filters": ["none", "warm", "cool"][1 % 3]}
