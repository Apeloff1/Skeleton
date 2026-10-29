"""Biome 0059.
"""
from __future__ import annotations

BIOME = "biome_0059"

def climate() -> dict:
    return {"id": BIOME, "temp": round((59 % 10) / 10, 2), "moisture": round(((59*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (59 % 3) == 0:
        out.append("heat")
    if (59 % 4) == 0:
        out.append("fog")
    return out or ["none"]
