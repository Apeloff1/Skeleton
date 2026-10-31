"""Environmental hazard.
Applies room-based damage or debuffs from biome and weather.
"""
from __future__ import annotations
from typing import Any, Dict

class EnvironmentalHazard:
    def apply(self, biome: str, weather_hazard_mult: float = 1.0, optical: float = 0.9) -> Dict[str, Any]:
        base = {"ash_tunnel": 2, "crystal_cavern": 4, "void_rift": 8, "ember_hall": 5}.get(biome, 3)
        dmg = int(base * weather_hazard_mult * (1.2 - optical * 0.3))
        effect = "slow" if biome == "ice_vault" else "burn" if biome == "ember_hall" else "ash"
        return {"damage": max(0, dmg), "effect": effect, "biome": biome}
