"""Biome 0065.
"""
from __future__ import annotations

BIOME = "biome_0065"

def climate() -> dict:
    return {"id": BIOME, "temp": round((65 % 10) / 10, 2), "moisture": round(((65*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (65 % 3) == 0:
        out.append("heat")
    if (65 % 4) == 0:
        out.append("fog")
    return out or ["none"]
