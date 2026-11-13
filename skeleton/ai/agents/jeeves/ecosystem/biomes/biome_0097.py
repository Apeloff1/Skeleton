"""Biome 0097.
"""
from __future__ import annotations

BIOME = "biome_0097"

def climate() -> dict:
    return {"id": BIOME, "temp": round((97 % 10) / 10, 2), "moisture": round(((97*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (97 % 3) == 0:
        out.append("heat")
    if (97 % 4) == 0:
        out.append("fog")
    return out or ["none"]
