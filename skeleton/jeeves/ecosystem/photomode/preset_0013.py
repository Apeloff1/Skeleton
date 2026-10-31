"""Photo preset 0013.
"""
from __future__ import annotations

PRESET = "photo_0013"

def capture(fov: float = 60.0) -> dict:
    return {"ok": True, "preset": PRESET, "fov": fov, "filters": ["none", "warm", "cool"][13 % 3]}
