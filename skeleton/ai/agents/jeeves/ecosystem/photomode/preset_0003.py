"""Photo preset 0003.
"""
from __future__ import annotations

PRESET = "photo_0003"

def capture(fov: float = 60.0) -> dict:
    return {"ok": True, "preset": PRESET, "fov": fov, "filters": ["none", "warm", "cool"][3 % 3]}
