"""Biome 0006.
"""
from __future__ import annotations

BIOME = "biome_0006"

def climate() -> dict:
    return {"id": BIOME, "temp": round((6 % 10) / 10, 2), "moisture": round(((6*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (6 % 3) == 0:
        out.append("heat")
    if (6 % 4) == 0:
        out.append("fog")
    return out or ["none"]
