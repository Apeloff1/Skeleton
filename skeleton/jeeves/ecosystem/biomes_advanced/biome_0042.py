"""Advanced biome 0042.
"""
from __future__ import annotations

BIOME = "adv_biome_0042"

def climate() -> dict:
    return {"temp": round((42 % 20) / 20, 2), "moisture": round(((42*7) % 20) / 20, 2), "wind": round((42 % 10) / 10, 2)}

def resources() -> list[str]:
    base = ["wood", "stone"]
    if 42 % 3 == 0:
        base.append("ore")
    if 42 % 5 == 0:
        base.append("crystal")
    return base
