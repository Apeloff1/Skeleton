"""Biome 0099.
"""
from __future__ import annotations

BIOME = "biome_0099"

def climate() -> dict:
    return {"id": BIOME, "temp": round((99 % 10) / 10, 2), "moisture": round(((99*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (99 % 3) == 0:
        out.append("heat")
    if (99 % 4) == 0:
        out.append("fog")
    return out or ["none"]
