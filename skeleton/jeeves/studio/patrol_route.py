"""Patrol route. Waypoint list for AI."""
from typing import Any, Dict, List, Tuple
class PatrolRoute:
    def __init__(self, points: List[Tuple[float, float]]):
        self.points = points
        self.idx = 0
    def next(self) -> Tuple[float, float]:
        self.idx = (self.idx + 1) % len(self.points)
        return self.points[self.idx]
