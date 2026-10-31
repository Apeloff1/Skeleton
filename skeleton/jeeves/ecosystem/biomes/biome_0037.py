"""Biome 0037.
"""
from __future__ import annotations

BIOME = "biome_0037"

def climate() -> dict:
    return {"id": BIOME, "temp": round((37 % 10) / 10, 2), "moisture": round(((37*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (37 % 3) == 0:
        out.append("heat")
    if (37 % 4) == 0:
        out.append("fog")
    return out or ["none"]
