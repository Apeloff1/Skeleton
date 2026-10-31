"""Biome 0023.
"""
from __future__ import annotations

BIOME = "biome_0023"

def climate() -> dict:
    return {"id": BIOME, "temp": round((23 % 10) / 10, 2), "moisture": round(((23*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (23 % 3) == 0:
        out.append("heat")
    if (23 % 4) == 0:
        out.append("fog")
    return out or ["none"]
