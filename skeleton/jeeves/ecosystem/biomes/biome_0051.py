"""Biome 0051.
"""
from __future__ import annotations

BIOME = "biome_0051"

def climate() -> dict:
    return {"id": BIOME, "temp": round((51 % 10) / 10, 2), "moisture": round(((51*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (51 % 3) == 0:
        out.append("heat")
    if (51 % 4) == 0:
        out.append("fog")
    return out or ["none"]
