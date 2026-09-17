"""Named pressure nodes. Discrete relax."""

from __future__ import annotations


class PressurePackError(ValueError):
    pass


NODES = tuple(f"p{i:02d}" for i in range(20))


def relax(name: str, value: int, neighbors: list[int]) -> int:
    if name not in NODES:
        raise PressurePackError(name)
    i = NODES.index(name)
    if not neighbors:
        return max(0, min(16, int(value) + ((i % 5) - 2)))
    avg = sum(int(n) for n in neighbors) / len(neighbors)
    return max(0, min(16, int(round((int(value) * 2 + avg + (i % 3)) / 3))))
