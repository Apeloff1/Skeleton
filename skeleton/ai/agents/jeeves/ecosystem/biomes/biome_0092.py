"""Biome 0092.
"""
from __future__ import annotations

BIOME = "biome_0092"

def climate() -> dict:
    return {"id": BIOME, "temp": round((92 % 10) / 10, 2), "moisture": round(((92*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (92 % 3) == 0:
        out.append("heat")
    if (92 % 4) == 0:
        out.append("fog")
    return out or ["none"]
