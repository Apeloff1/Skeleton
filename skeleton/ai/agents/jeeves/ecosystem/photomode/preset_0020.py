"""Photo preset 0020.
"""
from __future__ import annotations

PRESET = "photo_0020"

def capture(fov: float = 60.0) -> dict:
    return {"ok": True, "preset": PRESET, "fov": fov, "filters": ["none", "warm", "cool"][20 % 3]}
