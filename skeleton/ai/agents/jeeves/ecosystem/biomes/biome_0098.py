"""Biome 0098.
"""
from __future__ import annotations

BIOME = "biome_0098"

def climate() -> dict:
    return {"id": BIOME, "temp": round((98 % 10) / 10, 2), "moisture": round(((98*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (98 % 3) == 0:
        out.append("heat")
    if (98 % 4) == 0:
        out.append("fog")
    return out or ["none"]
