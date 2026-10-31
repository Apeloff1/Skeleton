"""Biome 0089.
"""
from __future__ import annotations

BIOME = "biome_0089"

def climate() -> dict:
    return {"id": BIOME, "temp": round((89 % 10) / 10, 2), "moisture": round(((89*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (89 % 3) == 0:
        out.append("heat")
    if (89 % 4) == 0:
        out.append("fog")
    return out or ["none"]
