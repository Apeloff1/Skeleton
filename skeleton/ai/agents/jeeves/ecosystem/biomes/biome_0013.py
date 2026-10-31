"""Biome 0013.
"""
from __future__ import annotations

BIOME = "biome_0013"

def climate() -> dict:
    return {"id": BIOME, "temp": round((13 % 10) / 10, 2), "moisture": round(((13*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (13 % 3) == 0:
        out.append("heat")
    if (13 % 4) == 0:
        out.append("fog")
    return out or ["none"]
