"""Biome 0090.
"""
from __future__ import annotations

BIOME = "biome_0090"

def climate() -> dict:
    return {"id": BIOME, "temp": round((90 % 10) / 10, 2), "moisture": round(((90*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (90 % 3) == 0:
        out.append("heat")
    if (90 % 4) == 0:
        out.append("fog")
    return out or ["none"]
