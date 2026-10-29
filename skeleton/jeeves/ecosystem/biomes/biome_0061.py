"""Biome 0061.
"""
from __future__ import annotations

BIOME = "biome_0061"

def climate() -> dict:
    return {"id": BIOME, "temp": round((61 % 10) / 10, 2), "moisture": round(((61*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (61 % 3) == 0:
        out.append("heat")
    if (61 % 4) == 0:
        out.append("fog")
    return out or ["none"]
