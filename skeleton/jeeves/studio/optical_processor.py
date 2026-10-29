"""Optical observation processor.
Tile classification, diversity scoring, feedback to level gen and distillation.
"""
from __future__ import annotations
from typing import Any, Dict, List
import math

class OpticalProcessor:
    def classify(self, diversity: float, steps: int) -> Dict[str, float]:
        return {
            "tile_floor": 0.4 + diversity * 0.1,
            "tile_wall": 0.2,
            "tile_hazard": 0.1 + (1-diversity)*0.05,
            "entity_pack": 0.15,
            "entity_player": 0.1,
            "entity_enemy": 0.05,
        }
    def score(self, classes: Dict[str, float]) -> float:
        return sum(v * (0.5 + i*0.1) for i, v in enumerate(classes.values()))
