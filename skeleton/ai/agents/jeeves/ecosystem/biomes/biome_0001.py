"""Biome 0001.
"""
from __future__ import annotations

BIOME = "biome_0001"

def climate() -> dict:
    return {"id": BIOME, "temp": round((1 % 10) / 10, 2), "moisture": round(((1*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (1 % 3) == 0:
        out.append("heat")
    if (1 % 4) == 0:
        out.append("fog")
    return out or ["none"]
