"""Biome 0046.
"""
from __future__ import annotations

BIOME = "biome_0046"

def climate() -> dict:
    return {"id": BIOME, "temp": round((46 % 10) / 10, 2), "moisture": round(((46*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (46 % 3) == 0:
        out.append("heat")
    if (46 % 4) == 0:
        out.append("fog")
    return out or ["none"]
