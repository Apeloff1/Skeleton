"""Biome 0083.
"""
from __future__ import annotations

BIOME = "biome_0083"

def climate() -> dict:
    return {"id": BIOME, "temp": round((83 % 10) / 10, 2), "moisture": round(((83*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (83 % 3) == 0:
        out.append("heat")
    if (83 % 4) == 0:
        out.append("fog")
    return out or ["none"]
