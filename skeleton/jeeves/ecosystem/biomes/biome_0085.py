"""Biome 0085.
"""
from __future__ import annotations

BIOME = "biome_0085"

def climate() -> dict:
    return {"id": BIOME, "temp": round((85 % 10) / 10, 2), "moisture": round(((85*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (85 % 3) == 0:
        out.append("heat")
    if (85 % 4) == 0:
        out.append("fog")
    return out or ["none"]
