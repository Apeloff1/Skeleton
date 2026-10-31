"""Biome 0094.
"""
from __future__ import annotations

BIOME = "biome_0094"

def climate() -> dict:
    return {"id": BIOME, "temp": round((94 % 10) / 10, 2), "moisture": round(((94*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (94 % 3) == 0:
        out.append("heat")
    if (94 % 4) == 0:
        out.append("fog")
    return out or ["none"]
