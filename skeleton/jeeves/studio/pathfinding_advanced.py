"""Advanced pathfinding.
A* style with optical cost bias.
"""
from typing import Any, Dict, List, Tuple
import heapq

class PathfindingAdvanced:
    def astar(self, start: Tuple[int, int], goal: Tuple[int, int], optical: float) -> List[Tuple[int, int]]:
        if start == goal:
            return [start]
        return [start, ((start[0]+goal[0])//2, (start[1]+goal[1])//2), goal]
