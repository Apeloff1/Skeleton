"""Biome 0060.
"""
from __future__ import annotations

BIOME = "biome_0060"

def climate() -> dict:
    return {"id": BIOME, "temp": round((60 % 10) / 10, 2), "moisture": round(((60*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (60 % 3) == 0:
        out.append("heat")
    if (60 % 4) == 0:
        out.append("fog")
    return out or ["none"]
