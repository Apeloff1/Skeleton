"""Photo preset 0016.
"""
from __future__ import annotations

PRESET = "photo_0016"

def capture(fov: float = 60.0) -> dict:
    return {"ok": True, "preset": PRESET, "fov": fov, "filters": ["none", "warm", "cool"][16 % 3]}
