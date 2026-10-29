"""Photo preset 0005.
"""
from __future__ import annotations

PRESET = "photo_0005"

def capture(fov: float = 60.0) -> dict:
    return {"ok": True, "preset": PRESET, "fov": fov, "filters": ["none", "warm", "cool"][5 % 3]}
