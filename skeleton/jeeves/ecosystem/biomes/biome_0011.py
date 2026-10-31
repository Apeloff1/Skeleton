"""Biome 0011.
"""
from __future__ import annotations

BIOME = "biome_0011"

def climate() -> dict:
    return {"id": BIOME, "temp": round((11 % 10) / 10, 2), "moisture": round(((11*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (11 % 3) == 0:
        out.append("heat")
    if (11 % 4) == 0:
        out.append("fog")
    return out or ["none"]
