"""Biome 0087.
"""
from __future__ import annotations

BIOME = "biome_0087"

def climate() -> dict:
    return {"id": BIOME, "temp": round((87 % 10) / 10, 2), "moisture": round(((87*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (87 % 3) == 0:
        out.append("heat")
    if (87 % 4) == 0:
        out.append("fog")
    return out or ["none"]
