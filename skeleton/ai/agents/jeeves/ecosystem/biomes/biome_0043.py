"""Biome 0043.
"""
from __future__ import annotations

BIOME = "biome_0043"

def climate() -> dict:
    return {"id": BIOME, "temp": round((43 % 10) / 10, 2), "moisture": round(((43*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (43 % 3) == 0:
        out.append("heat")
    if (43 % 4) == 0:
        out.append("fog")
    return out or ["none"]
