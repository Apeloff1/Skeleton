"""Biome 0012.
"""
from __future__ import annotations

BIOME = "biome_0012"

def climate() -> dict:
    return {"id": BIOME, "temp": round((12 % 10) / 10, 2), "moisture": round(((12*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (12 % 3) == 0:
        out.append("heat")
    if (12 % 4) == 0:
        out.append("fog")
    return out or ["none"]
