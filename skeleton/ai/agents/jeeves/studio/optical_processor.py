"""Optical observation processor (4x).
Tile classification, diversity scoring, feedback loops, multi-frame aggregation.
"""
from __future__ import annotations
from typing import Any, Dict, List
import math

class OpticalProcessor:
    def classify(self, diversity: float, steps: int) -> Dict[str, float]:
        base = {
            "tile_floor": 0.4 + diversity * 0.12,
            "tile_wall": 0.18 + (1-diversity)*0.04,
            "tile_hazard": 0.09 + (1-diversity)*0.06,
            "entity_pack": 0.14 + diversity * 0.03,
            "entity_player": 0.09,
            "entity_enemy": 0.06 + diversity * 0.02,
            "entity_boss": 0.04,
        }
        total = sum(base.values())
        return {k: v/total for k, v in base.items()}

    def score(self, classes: Dict[str, float]) -> float:
        weights = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1]
        return sum(v * weights[i % len(weights)] for i, v in enumerate(classes.values()))

    def aggregate(self, frames: List[Dict[str, float]]) -> Dict[str, float]:
        if not frames:
            return {}
        keys = frames[0].keys()
        return {k: sum(f.get(k, 0) for f in frames)/len(frames) for k in keys}
