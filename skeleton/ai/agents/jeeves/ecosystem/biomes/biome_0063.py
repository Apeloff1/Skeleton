"""Biome 0063.
"""
from __future__ import annotations

BIOME = "biome_0063"

def climate() -> dict:
    return {"id": BIOME, "temp": round((63 % 10) / 10, 2), "moisture": round(((63*3) % 10) / 10, 2)}

def hazards() -> list[str]:
    out = []
    if (63 % 3) == 0:
        out.append("heat")
    if (63 % 4) == 0:
        out.append("fog")
    return out or ["none"]
