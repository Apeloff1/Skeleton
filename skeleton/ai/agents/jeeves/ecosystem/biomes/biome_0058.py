"""Biome 0058.
"""
from __future__ import annotations

BIOME = "biome_0058"

def climate() -> dict:
    return {"id": BIOME, "temp": round((58 % 10) / 10, 2), "moisture": round(((58*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (58 % 3) == 0:
        out.append("heat")
    if (58 % 4) == 0:
        out.append("fog")
    return out or ["none"]
