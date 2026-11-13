"""Biome 0002.
"""
from __future__ import annotations

BIOME = "biome_0002"

def climate() -> dict:
    return {"id": BIOME, "temp": round((2 % 10) / 10, 2), "moisture": round(((2*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (2 % 3) == 0:
        out.append("heat")
    if (2 % 4) == 0:
        out.append("fog")
    return out or ["none"]
