"""Biome 0072.
"""
from __future__ import annotations

BIOME = "biome_0072"

def climate() -> dict:
    return {"id": BIOME, "temp": round((72 % 10) / 10, 2), "moisture": round(((72*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (72 % 3) == 0:
        out.append("heat")
    if (72 % 4) == 0:
        out.append("fog")
    return out or ["none"]
