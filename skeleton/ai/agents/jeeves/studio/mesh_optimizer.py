"""Mesh optimizer.
Simplifies vertex sets while preserving optical-weighted detail.
"""
from typing import Any, Dict, List, Tuple

class MeshOptimizer:
    def simplify(self, vertices: List[Tuple[float, float, float]], target: int, optical: float) -> List[Tuple[float, float, float]]:
        if len(vertices) <= target:
            return vertices
        step = max(1, int(len(vertices) / target * (1.1 - optical * 0.2)))
        return vertices[::step][:target]

    def bounds(self, vertices: List[Tuple[float, float, float]]) -> Dict[str, Any]:
        if not vertices:
            return {"min": (0,0,0), "max": (0,0,0)}
        xs, ys, zs = zip(*vertices)
        return {"min": (min(xs), min(ys), min(zs)), "max": (max(xs), max(ys), max(zs))}
