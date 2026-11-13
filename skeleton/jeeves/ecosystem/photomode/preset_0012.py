"""Photo preset 0012.
"""
from __future__ import annotations

PRESET = "photo_0012"

def capture(fov: float = 60.0) -> dict:
    return {"ok": True, "preset": PRESET, "fov": fov, "filters": ["none", "warm", "cool"][12 % 3]}
