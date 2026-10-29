"""Biome 0004.
"""
from __future__ import annotations

BIOME = "biome_0004"

def climate() -> dict:
    return {"id": BIOME, "temp": round((4 % 10) / 10, 2), "moisture": round(((4*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (4 % 3) == 0:
        out.append("heat")
    if (4 % 4) == 0:
        out.append("fog")
    return out or ["none"]
