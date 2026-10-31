"""Biome 0014.
"""
from __future__ import annotations

BIOME = "biome_0014"

def climate() -> dict:
    return {"id": BIOME, "temp": round((14 % 10) / 10, 2), "moisture": round(((14*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (14 % 3) == 0:
        out.append("heat")
    if (14 % 4) == 0:
        out.append("fog")
    return out or ["none"]
