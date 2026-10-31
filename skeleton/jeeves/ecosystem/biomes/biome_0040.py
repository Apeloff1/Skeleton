"""Biome 0040.
"""
from __future__ import annotations

BIOME = "biome_0040"

def climate() -> dict:
    return {"id": BIOME, "temp": round((40 % 10) / 10, 2), "moisture": round(((40*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (40 % 3) == 0:
        out.append("heat")
    if (40 % 4) == 0:
        out.append("fog")
    return out or ["none"]
