"""Biome 0034.
"""
from __future__ import annotations

BIOME = "biome_0034"

def climate() -> dict:
    return {"id": BIOME, "temp": round((34 % 10) / 10, 2), "moisture": round(((34*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (34 % 3) == 0:
        out.append("heat")
    if (34 % 4) == 0:
        out.append("fog")
    return out or ["none"]
