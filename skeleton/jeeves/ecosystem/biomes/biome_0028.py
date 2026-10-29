"""Biome 0028.
"""
from __future__ import annotations

BIOME = "biome_0028"

def climate() -> dict:
    return {"id": BIOME, "temp": round((28 % 10) / 10, 2), "moisture": round(((28*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (28 % 3) == 0:
        out.append("heat")
    if (28 % 4) == 0:
        out.append("fog")
    return out or ["none"]
