"""Biome 0021.
"""
from __future__ import annotations

BIOME = "biome_0021"

def climate() -> dict:
    return {"id": BIOME, "temp": round((21 % 10) / 10, 2), "moisture": round(((21*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (21 % 3) == 0:
        out.append("heat")
    if (21 % 4) == 0:
        out.append("fog")
    return out or ["none"]
