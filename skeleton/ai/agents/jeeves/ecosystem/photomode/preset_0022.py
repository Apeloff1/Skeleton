"""Photo preset 0022.
"""
from __future__ import annotations

PRESET = "photo_0022"

def capture(fov: float = 60.0) -> dict:
    return {"ok": True, "preset": PRESET, "fov": fov, "filters": ["none", "warm", "cool"][22 % 3]}
