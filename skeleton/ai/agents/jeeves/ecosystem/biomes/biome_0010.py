"""Biome 0010.
"""
from __future__ import annotations

BIOME = "biome_0010"

def climate() -> dict:
    return {"id": BIOME, "temp": round((10 % 10) / 10, 2), "moisture": round(((10*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (10 % 3) == 0:
        out.append("heat")
    if (10 % 4) == 0:
        out.append("fog")
    return out or ["none"]
