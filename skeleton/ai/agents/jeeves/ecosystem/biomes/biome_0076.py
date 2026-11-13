"""Biome 0076.
"""
from __future__ import annotations

BIOME = "biome_0076"

def climate() -> dict:
    return {"id": BIOME, "temp": round((76 % 10) / 10, 2), "moisture": round(((76*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (76 % 3) == 0:
        out.append("heat")
    if (76 % 4) == 0:
        out.append("fog")
    return out or ["none"]
