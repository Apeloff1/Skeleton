"""Biome 0009.
"""
from __future__ import annotations

BIOME = "biome_0009"

def climate() -> dict:
    return {"id": BIOME, "temp": round((9 % 10) / 10, 2), "moisture": round(((9*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (9 % 3) == 0:
        out.append("heat")
    if (9 % 4) == 0:
        out.append("fog")
    return out or ["none"]
