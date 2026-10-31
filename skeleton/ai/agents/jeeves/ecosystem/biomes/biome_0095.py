"""Biome 0095.
"""
from __future__ import annotations

BIOME = "biome_0095"

def climate() -> dict:
    return {"id": BIOME, "temp": round((95 % 10) / 10, 2), "moisture": round(((95*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (95 % 3) == 0:
        out.append("heat")
    if (95 % 4) == 0:
        out.append("fog")
    return out or ["none"]
