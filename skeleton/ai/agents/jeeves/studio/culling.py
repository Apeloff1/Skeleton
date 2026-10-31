"""Culling.
Frustum and optical culling for draw calls.
"""
from typing import Any, Dict, List, Tuple

class Culling:
    def frustum(self, points: List[Tuple[float, float]], view: Tuple[float, float, float, float]) -> List[Tuple[float, float]]:
        x, y, w, h = view
        return [p for p in points if x <= p[0] <= x + w and y <= p[1] <= y + h]

    def optical_cull(self, count: int, optical: float) -> int:
        return max(1, int(count * (0.5 + optical * 0.5)))
