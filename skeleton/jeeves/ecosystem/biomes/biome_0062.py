"""Biome 0062.
"""
from __future__ import annotations

BIOME = "biome_0062"

def climate() -> dict:
    return {"id": BIOME, "temp": round((62 % 10) / 10, 2), "moisture": round(((62*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (62 % 3) == 0:
        out.append("heat")
    if (62 % 4) == 0:
        out.append("fog")
    return out or ["none"]
