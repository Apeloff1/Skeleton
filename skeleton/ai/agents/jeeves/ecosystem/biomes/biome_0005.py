"""Biome 0005.
"""
from __future__ import annotations

BIOME = "biome_0005"

def climate() -> dict:
    return {"id": BIOME, "temp": round((5 % 10) / 10, 2), "moisture": round(((5*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (5 % 3) == 0:
        out.append("heat")
    if (5 % 4) == 0:
        out.append("fog")
    return out or ["none"]
