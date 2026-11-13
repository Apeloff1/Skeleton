"""Photo preset 0026.
"""
from __future__ import annotations

PRESET = "photo_0026"

def capture(fov: float = 60.0) -> dict:
    return {"ok": True, "preset": PRESET, "fov": fov, "filters": ["none", "warm", "cool"][26 % 3]}
