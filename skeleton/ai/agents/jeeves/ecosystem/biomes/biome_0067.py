"""Biome 0067.
"""
from __future__ import annotations

BIOME = "biome_0067"

def climate() -> dict:
    return {"id": BIOME, "temp": round((67 % 10) / 10, 2), "moisture": round(((67*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (67 % 3) == 0:
        out.append("heat")
    if (67 % 4) == 0:
        out.append("fog")
    return out or ["none"]
