"""Biome 0025.
"""
from __future__ import annotations

BIOME = "biome_0025"

def climate() -> dict:
    return {"id": BIOME, "temp": round((25 % 10) / 10, 2), "moisture": round(((25*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (25 % 3) == 0:
        out.append("heat")
    if (25 % 4) == 0:
        out.append("fog")
    return out or ["none"]
