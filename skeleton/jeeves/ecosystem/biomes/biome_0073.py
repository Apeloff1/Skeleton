"""Biome 0073.
"""
from __future__ import annotations

BIOME = "biome_0073"

def climate() -> dict:
    return {"id": BIOME, "temp": round((73 % 10) / 10, 2), "moisture": round(((73*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (73 % 3) == 0:
        out.append("heat")
    if (73 % 4) == 0:
        out.append("fog")
    return out or ["none"]
