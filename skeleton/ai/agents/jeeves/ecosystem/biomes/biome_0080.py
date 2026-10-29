"""Biome 0080.
"""
from __future__ import annotations

BIOME = "biome_0080"

def climate() -> dict:
    return {"id": BIOME, "temp": round((80 % 10) / 10, 2), "moisture": round(((80*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (80 % 3) == 0:
        out.append("heat")
    if (80 % 4) == 0:
        out.append("fog")
    return out or ["none"]
