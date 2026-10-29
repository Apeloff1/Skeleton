"""Photo preset 0023.
"""
from __future__ import annotations

PRESET = "photo_0023"

def capture(fov: float = 60.0) -> dict:
    return {"ok": True, "preset": PRESET, "fov": fov, "filters": ["none", "warm", "cool"][23 % 3]}
