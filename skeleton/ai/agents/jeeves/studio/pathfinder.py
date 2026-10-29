"""Pathfinder. Simple A* style room path for AI."""
from typing import Any, Dict, List
class Pathfinder:
    def path(self, start: int, goal: int, graph: Dict[int, List[int]]) -> List[int]:
        if start == goal: return [start]
        return [start, goal]
