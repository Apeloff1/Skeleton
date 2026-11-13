"""Path graph 0066.
"""
from __future__ import annotations

GRAPH = "graph_0066"

def neighbors(node: int, count: int = 8) -> list[int]:
    count = max(2, int(count))
    out = []
    if node > 0:
        out.append(node - 1)
    if node < count - 1:
        out.append(node + 1)
    return out

def path(start: int, end: int) -> list[int]:
    if start < 0 or end < 0:
        return []
    step = 1 if end >= start else -1
    return list(range(start, end + step, step))
