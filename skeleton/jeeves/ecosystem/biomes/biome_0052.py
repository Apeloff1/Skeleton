"""Biome 0052.
"""
from __future__ import annotations

BIOME = "biome_0052"

def climate() -> dict:
    return {"id": BIOME, "temp": round((52 % 10) / 10, 2), "moisture": round(((52*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (52 % 3) == 0:
        out.append("heat")
    if (52 % 4) == 0:
        out.append("fog")
    return out or ["none"]
