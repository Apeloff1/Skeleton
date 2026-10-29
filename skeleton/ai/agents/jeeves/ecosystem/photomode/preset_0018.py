"""Photo preset 0018.
"""
from __future__ import annotations

PRESET = "photo_0018"

def capture(fov: float = 60.0) -> dict:
    return {"ok": True, "preset": PRESET, "fov": fov, "filters": ["none", "warm", "cool"][18 % 3]}
