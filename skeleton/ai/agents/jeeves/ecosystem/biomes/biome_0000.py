"""Biome 0000.
"""
from __future__ import annotations

BIOME = "biome_0000"

def climate() -> dict:
    return {"id": BIOME, "temp": round((0 % 10) / 10, 2), "moisture": round(((0*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (0 % 3) == 0:
        out.append("heat")
    if (0 % 4) == 0:
        out.append("fog")
    return out or ["none"]
