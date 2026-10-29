"""Advanced biome 0067.
"""
from __future__ import annotations

BIOME = "adv_biome_0067"

def climate() -> dict:
    return {"temp": round((67 % 20) / 20, 2), "moisture": round(((67*7) % 20) / 20, 2), "wind": round((67 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 67 % 3 == 0:
        base.append("ore")
    if 67 % 5 == 0:
        base.append("crystal")
    return base
