"""Layout shape metrics with limits: critical-path share, dead-end ratio, loop count."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .errors import ProcgenError


@dataclass(frozen=True)
class LayoutLimits:
    min_critical_share: float = 0.2    # path rooms / all rooms; below -> mostly detours
    max_critical_share: float = 1.0
    max_dead_end_ratio: float = 0.6    # dead-end rooms (degree 1, not start/goal) / all rooms
    max_loops: int = 12                # independent cycles (E - V + components)
    max_key_distance: int = 4          # door steps from a key's room to its lock

    def __post_init__(self) -> None:
        if not 0.0 <= self.min_critical_share <= self.max_critical_share <= 1.0:
            raise ProcgenError("need 0 <= min_critical_share <= max_critical_share <= 1")
        if not 0.0 <= self.max_dead_end_ratio <= 1.0 or self.max_loops < 0 or self.max_key_distance < 1:
            raise ProcgenError("dead-end ratio in [0, 1], max_loops >= 0, max_key_distance >= 1")

    def as_dict(self) -> dict:
        return {"min_critical_share": self.min_critical_share, "max_critical_share": self.max_critical_share,
                "max_dead_end_ratio": self.max_dead_end_ratio, "max_loops": self.max_loops,
                "max_key_distance": self.max_key_distance}

    @classmethod
    def from_mapping(cls, data: Mapping | None) -> "LayoutLimits":
        if not isinstance(data, Mapping):
            return cls()
        known = set(cls().as_dict())
        return cls(**{k: v for k, v in data.items() if k in known})


def layout_metrics(adj: Mapping[str, list[str]], critical_path, start: str, goal: str) -> dict:
    """Metrics on an undirected room graph (``adj`` symmetric or not; edges are de-duplicated)."""
    nodes = set(adj)
    edges = {tuple(sorted((a, b))) for a, outs in adj.items() for b in outs if b in nodes and a != b}
    und: dict[str, set[str]] = {n: set() for n in nodes}
    for a, b in edges:
        und[a].add(b)
        und[b].add(a)
    comps, seen = 0, set()
    for n in sorted(nodes):
        if n in seen:
            continue
        comps += 1
        stack = [n]
        seen.add(n)
        while stack:
            for m in und[stack.pop()]:
                if m not in seen:
                    seen.add(m)
                    stack.append(m)
    v = len(nodes) or 1
    dead = sorted(n for n in nodes if len(und[n]) == 1 and n not in (start, goal))
    path = [r for r in critical_path if r in nodes]
    return {"rooms": len(nodes), "critical_path_share": round(len(path) / v, 6),
            "dead_end_ratio": round(len(dead) / v, 6), "dead_ends": dead,
            "loops": len(edges) - len(nodes) + comps}


def metric_violations(m: Mapping, limits: LayoutLimits) -> list[str]:
    out = []
    if not limits.min_critical_share <= m["critical_path_share"] <= limits.max_critical_share:
        out.append(f"critical-path share {m['critical_path_share']:.2f} outside "
                   f"[{limits.min_critical_share}, {limits.max_critical_share}]")
    if m["dead_end_ratio"] > limits.max_dead_end_ratio:
        out.append(f"dead-end ratio {m['dead_end_ratio']:.2f} above {limits.max_dead_end_ratio}")
    if m["loops"] > limits.max_loops:
        out.append(f"{m['loops']} loops above {limits.max_loops}")
    return out
