"""Biome 0041.
"""
from __future__ import annotations

BIOME = "biome_0041"

def climate() -> dict:
    return {"id": BIOME, "temp": round((41 % 10) / 10, 2), "moisture": round(((41*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (41 % 3) == 0:
        out.append("heat")
    if (41 % 4) == 0:
        out.append("fog")
    return out or ["none"]
