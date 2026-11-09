"""Regular dodecahedron as a 12-face game-system lattice.

The dual of the icosahedron: 12 pentagonal faces (systems), 20 vertices
(oracle mouths), 30 edges. Face adjacency is the icosahedral graph
(degree 5). Activation is the softmax of a linear map from the 10-cube
onto the 12 faces — Byzantine, but deterministic.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from skeleton.context.tensor import AXES, ContextTensor

PHI = (1.0 + math.sqrt(5.0)) / 2.0

FACES: Tuple[str, ...] = (
    "combat", "heat", "loot", "forge", "extract", "narrative",
    "ai", "world", "economy", "ui", "audio", "meta",
)

# Icosahedral graph on 12 vertices = dodeca face adjacency.
ADJ: Tuple[Tuple[int, ...], ...] = (
    (1, 2, 3, 4, 5),
    (0, 2, 5, 6, 7),
    (0, 1, 3, 7, 8),
    (0, 2, 4, 8, 9),
    (0, 3, 5, 9, 10),
    (0, 1, 4, 6, 10),
    (1, 5, 7, 10, 11),
    (1, 2, 6, 8, 11),
    (2, 3, 7, 9, 11),
    (3, 4, 8, 10, 11),
    (4, 5, 6, 9, 11),
    (6, 7, 8, 9, 10),
)

# 20 vertices of a regular dodecahedron (cube ± golden-ratio belts).
def _vertices() -> Tuple[Tuple[float, float, float], ...]:
    cube = [(sx, sy, sz) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    belts = []
    for coords in (
        [(0, sy / PHI, sz * PHI) for sy in (-1, 1) for sz in (-1, 1)],
        [(sx * PHI, 0, sz / PHI) for sx in (-1, 1) for sz in (-1, 1)],
        [(sx / PHI, sy * PHI, 0) for sx in (-1, 1) for sy in (-1, 1)],
    ):
        belts.extend(coords)
    return tuple(cube + belts)


VERTICES: Tuple[Tuple[float, float, float], ...] = _vertices()

# 10×12 projection: each face listens to two axes (wraps).
_WEIGHTS: Tuple[Tuple[float, ...], ...] = tuple(
    tuple(0.55 if (f + a) % 5 == 0 else 0.25 if (f + a) % 3 == 0 else 0.08
          for a in range(len(AXES)))
    for f in range(12)
)


def _softmax(xs: Sequence[float], temperature: float = 0.45) -> List[float]:
    peak = max(xs)
    exps = [math.exp((x - peak) / max(temperature, 1e-6)) for x in xs]
    z = sum(exps) or 1.0
    return [e / z for e in exps]


@dataclass
class Dodecahedron:
    activations: Tuple[float, ...]
    era: str

    @classmethod
    def from_tensor(cls, tensor: ContextTensor) -> "Dodecahedron":
        raw = []
        for f in range(12):
            raw.append(sum(w * v for w, v in zip(_WEIGHTS[f], tensor.values)))
        act = _softmax(raw)
        return cls(tuple(act), era=tensor.era)

    def face(self, name: str) -> float:
        return self.activations[FACES.index(name)]

    def neighbours(self, name: str) -> List[str]:
        i = FACES.index(name)
        return [FACES[j] for j in ADJ[i]]

    def hottest(self, n: int = 3) -> List[Tuple[str, float]]:
        ranked = sorted(zip(FACES, self.activations), key=lambda kv: -kv[1])
        return ranked[:n]

    def geodesic(self, a: str, b: str) -> int:
        """Unweighted BFS distance on the icosahedral graph."""
        s, t = FACES.index(a), FACES.index(b)
        if s == t:
            return 0
        seen = {s}
        frontier = [s]
        dist = 0
        while frontier:
            dist += 1
            nxt = []
            for u in frontier:
                for v in ADJ[u]:
                    if v == t:
                        return dist
                    if v not in seen:
                        seen.add(v)
                        nxt.append(v)
            frontier = nxt
        return -1

    def to_dict(self) -> Dict[str, object]:
        return {
            "era": self.era,
            "faces": {n: round(v, 4) for n, v in zip(FACES, self.activations)},
            "hottest": [{"face": n, "p": round(v, 4)} for n, v in self.hottest()],
            "vertices": 20,
            "edges": 30,
        }
