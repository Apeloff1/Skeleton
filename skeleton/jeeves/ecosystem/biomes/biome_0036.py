"""Biome 0036.
"""
from __future__ import annotations

BIOME = "biome_0036"

def climate() -> dict:
    return {"id": BIOME, "temp": round((36 % 10) / 10, 2), "moisture": round(((36*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (36 % 3) == 0:
        out.append("heat")
    if (36 % 4) == 0:
        out.append("fog")
    return out or ["none"]
