"""Biome 0066.
"""
from __future__ import annotations

BIOME = "biome_0066"

def climate() -> dict:
    return {"id": BIOME, "temp": round((66 % 10) / 10, 2), "moisture": round(((66*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (66 % 3) == 0:
        out.append("heat")
    if (66 % 4) == 0:
        out.append("fog")
    return out or ["none"]
