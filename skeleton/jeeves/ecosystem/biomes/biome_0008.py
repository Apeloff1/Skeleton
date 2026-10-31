"""Biome 0008.
"""
from __future__ import annotations

BIOME = "biome_0008"

def climate() -> dict:
    return {"id": BIOME, "temp": round((8 % 10) / 10, 2), "moisture": round(((8*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (8 % 3) == 0:
        out.append("heat")
    if (8 % 4) == 0:
        out.append("fog")
    return out or ["none"]
