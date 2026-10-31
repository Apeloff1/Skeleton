"""Photo preset 0007.
"""
from __future__ import annotations

PRESET = "photo_0007"

def capture(fov: float = 60.0) -> dict:
    return {"ok": True, "preset": PRESET, "fov": fov, "filters": ["none", "warm", "cool"][7 % 3]}
