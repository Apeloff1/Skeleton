"""Photo preset 0017.
"""
from __future__ import annotations

PRESET = "photo_0017"

def capture(fov: float = 60.0) -> dict:
    return {"ok": True, "preset": PRESET, "fov": fov, "filters": ["none", "warm", "cool"][17 % 3]}
