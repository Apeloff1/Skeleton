"""Biome 0044.
"""
from __future__ import annotations

BIOME = "biome_0044"

def climate() -> dict:
    return {"id": BIOME, "temp": round((44 % 10) / 10, 2), "moisture": round(((44*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (44 % 3) == 0:
        out.append("heat")
    if (44 % 4) == 0:
        out.append("fog")
    return out or ["none"]
