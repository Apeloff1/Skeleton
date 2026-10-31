"""Biome 0015.
"""
from __future__ import annotations

BIOME = "biome_0015"

def climate() -> dict:
    return {"id": BIOME, "temp": round((15 % 10) / 10, 2), "moisture": round(((15*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (15 % 3) == 0:
        out.append("heat")
    if (15 % 4) == 0:
        out.append("fog")
    return out or ["none"]
