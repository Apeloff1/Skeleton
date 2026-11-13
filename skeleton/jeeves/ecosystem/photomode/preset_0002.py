"""Photo preset 0002.
"""
from __future__ import annotations

PRESET = "photo_0002"

def capture(fov: float = 60.0) -> dict:
    return {"ok": True, "preset": PRESET, "fov": fov, "filters": ["none", "warm", "cool"][2 % 3]}
