"""Biome 0026.
"""
from __future__ import annotations

BIOME = "biome_0026"

def climate() -> dict:
    return {"id": BIOME, "temp": round((26 % 10) / 10, 2), "moisture": round(((26*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (26 % 3) == 0:
        out.append("heat")
    if (26 % 4) == 0:
        out.append("fog")
    return out or ["none"]
