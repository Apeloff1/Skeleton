"""Advanced biome 0032.
"""
from __future__ import annotations

BIOME = "adv_biome_0032"

def climate() -> dict:
    return {"temp": round((32 % 20) / 20, 2), "moisture": round(((32*7) % 20) / 20, 2), "wind": round((32 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 32 % 3 == 0:
        base.append("ore")
    if 32 % 5 == 0:
        base.append("crystal")
    return base
