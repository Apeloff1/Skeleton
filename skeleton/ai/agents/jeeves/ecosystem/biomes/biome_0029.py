"""Biome 0029.
"""
from __future__ import annotations

BIOME = "biome_0029"

def climate() -> dict:
    return {"id": BIOME, "temp": round((29 % 10) / 10, 2), "moisture": round(((29*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (29 % 3) == 0:
        out.append("heat")
    if (29 % 4) == 0:
        out.append("fog")
    return out or ["none"]
