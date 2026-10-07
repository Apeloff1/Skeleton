"""Spine topology: path graph, adjacency, connectivity invariants."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from skeleton.spine.law import SEGMENT_N, TOPOLOGY_KIND, VERTEBRA_N
from skeleton.spine.taxonomy import CATALOG, all_labels, junction_labels


@dataclass(frozen=True, slots=True)
class Edge:
    a: str
    b: str
    index: int

    @property
    def label(self) -> str:
        return f"{self.a}-{self.b}"


@dataclass(frozen=True, slots=True)
class SpineGraph:
    vertices: tuple[str, ...]
    edges: tuple[Edge, ...]
    kind: str = TOPOLOGY_KIND

    @property
    def n_vertices(self) -> int:
        return len(self.vertices)

    @property
    def n_edges(self) -> int:
        return len(self.edges)


def path_edges() -> tuple[Edge, ...]:
    labels = all_labels()
    return tuple(Edge(labels[i], labels[i + 1], i) for i in range(len(labels) - 1))


def spine_graph() -> SpineGraph:
    return SpineGraph(vertices=tuple(all_labels()), edges=path_edges())


def adjacency_list(graph: SpineGraph | None = None) -> dict[str, list[str]]:
    g = graph or spine_graph()
    adj: dict[str, list[str]] = {v: [] for v in g.vertices}
    for e in g.edges:
        adj[e.a].append(e.b)
        adj[e.b].append(e.a)
    return adj


def degree_map(graph: SpineGraph | None = None) -> dict[str, int]:
    adj = adjacency_list(graph)
    return {k: len(v) for k, v in adj.items()}


def is_path_graph(graph: SpineGraph | None = None) -> bool:
    g = graph or spine_graph()
    if g.n_vertices != VERTEBRA_N or g.n_edges != SEGMENT_N:
        return False
    deg = degree_map(g)
    ends = [v for v, d in deg.items() if d == 1]
    mids = [v for v, d in deg.items() if d == 2]
    if len(ends) != 2 or len(mids) != VERTEBRA_N - 2:
        return False
    # ends must be C1 and Co4
    labels = list(g.vertices)
    return set(ends) == {labels[0], labels[-1]}


def has_cycle(graph: SpineGraph | None = None) -> bool:
    """Path graphs are acyclic; detect via DFS back-edge."""
    g = graph or spine_graph()
    adj = adjacency_list(g)
    seen: set[str] = set()

    def dfs(u: str, parent: str | None) -> bool:
        seen.add(u)
        for v in adj[u]:
            if v == parent:
                continue
            if v in seen:
                return True
            if dfs(v, u):
                return True
        return False

    for v in g.vertices:
        if v not in seen:
            if dfs(v, None):
                return True
    return False


def connected_components(graph: SpineGraph | None = None) -> list[list[str]]:
    g = graph or spine_graph()
    adj = adjacency_list(g)
    seen: set[str] = set()
    comps: list[list[str]] = []
    for start in g.vertices:
        if start in seen:
            continue
        stack = [start]
        comp: list[str] = []
        seen.add(start)
        while stack:
            u = stack.pop()
            comp.append(u)
            for v in adj[u]:
                if v not in seen:
                    seen.add(v)
                    stack.append(v)
        comps.append(comp)
    return comps


def is_connected(graph: SpineGraph | None = None) -> bool:
    return len(connected_components(graph)) == 1


def shortest_path(a: str, b: str, graph: SpineGraph | None = None) -> list[str]:
    g = graph or spine_graph()
    adj = adjacency_list(g)
    if a not in adj or b not in adj:
        raise KeyError("vertex")
    prev: dict[str, str | None] = {a: None}
    queue = [a]
    i = 0
    while i < len(queue):
        u = queue[i]
        i += 1
        if u == b:
            break
        for v in adj[u]:
            if v not in prev:
                prev[v] = u
                queue.append(v)
    if b not in prev:
        raise ValueError("unreachable")
    path = [b]
    while path[-1] != a:
        path.append(prev[path[-1]])  # type: ignore[arg-type]
    path.reverse()
    return path


def path_distance(a: str, b: str) -> int:
    return len(shortest_path(a, b)) - 1


def junction_edges() -> list[Edge]:
    edges = {e.label: e for e in path_edges()}
    out: list[Edge] = []
    for a, b in junction_labels():
        out.append(edges[f"{a}-{b}"])
    return out


def validate_topology() -> dict[str, int]:
    g = spine_graph()
    if not is_path_graph(g):
        raise AssertionError("not-path")
    if has_cycle(g):
        raise AssertionError("cycle")
    if not is_connected(g):
        raise AssertionError("disconnected")
    return {"vertices": g.n_vertices, "edges": g.n_edges, "components": 1}


def subgraph_region(region_labels: Sequence[str]) -> SpineGraph:
    labels = list(region_labels)
    label_set = set(labels)
    edges = [e for e in path_edges() if e.a in label_set and e.b in label_set]
    return SpineGraph(vertices=tuple(labels), edges=tuple(edges), kind="region-path")
