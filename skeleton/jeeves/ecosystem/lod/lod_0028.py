"""LOD 0028.
"""
from __future__ import annotations

LOD = "lod_0028"

def level(distance: float) -> int:
    if distance < 10:
        return 0
    if distance < 30:
        return 1
    return 2

def mesh(level: int) -> str:
    return f"{LOD}_l{level}"
