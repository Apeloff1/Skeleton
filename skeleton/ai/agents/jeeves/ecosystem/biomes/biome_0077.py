"""Biome 0077.
"""
from __future__ import annotations

BIOME = "biome_0077"

def climate() -> dict:
    return {"id": BIOME, "temp": round((77 % 10) / 10, 2), "moisture": round(((77*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (77 % 3) == 0:
        out.append("heat")
    if (77 % 4) == 0:
        out.append("fog")
    return out or ["none"]
