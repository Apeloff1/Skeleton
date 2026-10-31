"""Biome 0030.
"""
from __future__ import annotations

BIOME = "biome_0030"

def climate() -> dict:
    return {"id": BIOME, "temp": round((30 % 10) / 10, 2), "moisture": round(((30*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (30 % 3) == 0:
        out.append("heat")
    if (30 % 4) == 0:
        out.append("fog")
    return out or ["none"]
