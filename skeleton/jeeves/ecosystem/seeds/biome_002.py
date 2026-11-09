"""Biome seed 002.
"""
from __future__ import annotations

BIOME_ID = "biome_002"
TEMPERATURE = round((2 % 10) / 10.0, 2)
MOISTURE = round(((2 * 3) % 10) / 10.0, 2)

def climate() -> dict:
    return {"id": BIOME_ID, "temp": TEMPERATURE, "moisture": MOISTURE}

def features() -> list[str]:
    base = ["ground", "sky"]
    if TEMPERATURE > 0.6:
        base.append("heat")
    if MOISTURE > 0.6:
        base.append("rain")
    return base
