"""Advanced biome 0058.
"""
from __future__ import annotations

BIOME = "adv_biome_0058"

def climate() -> dict:
    return {"temp": round((58 % 20) / 20, 2), "moisture": round(((58*7) % 20) / 20, 2), "wind": round((58 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 58 % 3 == 0:
        base.append("ore")
    if 58 % 5 == 0:
        base.append("crystal")
    return base
