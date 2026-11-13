"""Biome 0024.
"""
from __future__ import annotations

BIOME = "biome_0024"

def climate() -> dict:
    return {"id": BIOME, "temp": round((24 % 10) / 10, 2), "moisture": round(((24*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (24 % 3) == 0:
        out.append("heat")
    if (24 % 4) == 0:
        out.append("fog")
    return out or ["none"]
