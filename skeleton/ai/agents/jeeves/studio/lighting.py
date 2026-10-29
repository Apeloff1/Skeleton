"""Lighting.
Point and optical-modulated ambient.
"""
from typing import Any, Dict, Tuple
import math

class Lighting:
    def point(self, pos: Tuple[float, float], light: Tuple[float, float], intensity: float, optical: float) -> float:
        dx, dy = pos[0] - light[0], pos[1] - light[1]
        dist = math.sqrt(dx*dx + dy*dy) + 0.01
        return min(1.0, intensity * optical / dist)
