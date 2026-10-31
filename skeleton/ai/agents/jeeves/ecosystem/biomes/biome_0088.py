"""Biome 0088.
"""
from __future__ import annotations

BIOME = "biome_0088"

def climate() -> dict:
    return {"id": BIOME, "temp": round((88 % 10) / 10, 2), "moisture": round(((88*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (88 % 3) == 0:
        out.append("heat")
    if (88 % 4) == 0:
        out.append("fog")
    return out or ["none"]
