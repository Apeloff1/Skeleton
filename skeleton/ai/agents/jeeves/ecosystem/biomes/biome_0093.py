"""Biome 0093.
"""
from __future__ import annotations

BIOME = "biome_0093"

def climate() -> dict:
    return {"id": BIOME, "temp": round((93 % 10) / 10, 2), "moisture": round(((93*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (93 % 3) == 0:
        out.append("heat")
    if (93 % 4) == 0:
        out.append("fog")
    return out or ["none"]
