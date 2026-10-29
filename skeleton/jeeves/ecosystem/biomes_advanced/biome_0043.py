"""Advanced biome 0043.
"""
from __future__ import annotations

BIOME = "adv_biome_0043"

def climate() -> dict:
    return {"temp": round((43 % 20) / 20, 2), "moisture": round(((43*7) % 20) / 20, 2), "wind": round((43 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 43 % 3 == 0:
        base.append("ore")
    if 43 % 5 == 0:
        base.append("crystal")
    return base
