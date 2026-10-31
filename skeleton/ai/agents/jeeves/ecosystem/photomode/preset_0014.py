"""Photo preset 0014.
"""
from __future__ import annotations

PRESET = "photo_0014"

def capture(fov: float = 60.0) -> dict:
    return {"ok": True, "preset": PRESET, "fov": fov, "filters": ["none", "warm", "cool"][14 % 3]}
