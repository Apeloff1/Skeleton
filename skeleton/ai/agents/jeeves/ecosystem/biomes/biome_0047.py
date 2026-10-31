"""Biome 0047.
"""
from __future__ import annotations

BIOME = "biome_0047"

def climate() -> dict:
    return {"id": BIOME, "temp": round((47 % 10) / 10, 2), "moisture": round(((47*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (47 % 3) == 0:
        out.append("heat")
    if (47 % 4) == 0:
        out.append("fog")
    return out or ["none"]
