"""Advanced biome 0028.
"""
from __future__ import annotations

BIOME = "adv_biome_0028"

def climate() -> dict:
    return {"temp": round((28 % 20) / 20, 2), "moisture": round(((28*7) % 20) / 20, 2), "wind": round((28 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 28 % 3 == 0:
        base.append("ore")
    if 28 % 5 == 0:
        base.append("crystal")
    return base
