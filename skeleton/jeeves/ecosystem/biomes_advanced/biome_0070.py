"""Advanced biome 0070.
"""
from __future__ import annotations

BIOME = "adv_biome_0070"

def climate() -> dict:
    return {"temp": round((70 % 20) / 20, 2), "moisture": round(((70*7) % 20) / 20, 2), "wind": round((70 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 70 % 3 == 0:
        base.append("ore")
    if 70 % 5 == 0:
        base.append("crystal")
    return base
