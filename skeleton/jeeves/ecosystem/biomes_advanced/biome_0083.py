"""Advanced biome 0083.
"""
from __future__ import annotations

BIOME = "adv_biome_0083"

def climate() -> dict:
    return {"temp": round((83 % 20) / 20, 2), "moisture": round(((83*7) % 20) / 20, 2), "wind": round((83 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 83 % 3 == 0:
        base.append("ore")
    if 83 % 5 == 0:
        base.append("crystal")
    return base
