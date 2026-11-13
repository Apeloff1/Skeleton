"""Biome 0017.
"""
from __future__ import annotations

BIOME = "biome_0017"

def climate() -> dict:
    return {"id": BIOME, "temp": round((17 % 10) / 10, 2), "moisture": round(((17*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (17 % 3) == 0:
        out.append("heat")
    if (17 % 4) == 0:
        out.append("fog")
    return out or ["none"]
