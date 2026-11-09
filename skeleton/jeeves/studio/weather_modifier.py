"""Weather modifier.
Optical and biome-driven conditions that alter salvage, hazard, and visibility.
"""
from __future__ import annotations
from typing import Any, Dict

class WeatherModifier:
    def current(self, optical: float, biome: str = "ash_tunnel") -> Dict[str, Any]:
        if optical > 0.95:
            cond = "clear"
            salvage_mult = 1.15
            hazard_mult = 0.8
        elif optical > 0.85:
            cond = "haze"
            salvage_mult = 1.0
            hazard_mult = 1.0
        else:
            cond = "ash_storm"
            salvage_mult = 0.75
            hazard_mult = 1.4
        if biome == "void_rift":
            hazard_mult *= 1.2
        return {
            "condition": cond,
            "salvage_mult": round(salvage_mult, 2),
            "hazard_mult": round(hazard_mult, 2),
            "visibility": round(optical, 2),
        }
