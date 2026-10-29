"""Biome 0039.
"""
from __future__ import annotations

BIOME = "biome_0039"

def climate() -> dict:
    return {"id": BIOME, "temp": round((39 % 10) / 10, 2), "moisture": round(((39*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (39 % 3) == 0:
        out.append("heat")
    if (39 % 4) == 0:
        out.append("fog")
    return out or ["none"]
