"""Bounded dependency, strongly-connected-component, and graph reachability primitives."""
from collections import deque
from .errors import ContractError

def normalize(edges: dict[str, list[str]], *, max_nodes: int=20000, max_edges: int=100000) -> dict[str, tuple[str, ...]]:
    if not isinstance(edges, dict) or len(edges) > max_nodes:
        raise ContractError('invalid graph size')
    keys = set(edges)
    if any((not isinstance(k, str) or not k for k in keys)):
        raise ContractError('invalid graph node')
    normalized: dict[str, tuple[str, ...]] = {}
    count = 0
    for key, refs in edges.items():
        if not isinstance(refs, list) or any((not isinstance(ref, str) or ref not in keys for ref in refs)) or len(refs) != len(set(refs)):
            raise ContractError(f'invalid edges at {key}')
        count += len(refs)
        if count > max_edges:
            raise ContractError('too many graph edges')
        normalized[key] = tuple(sorted(refs))
    return normalized

def topological(edges: dict[str, list[str]]) -> list[str]:
    graph = normalize(edges)
    indegree = {k: len(refs) for k, refs in graph.items()}
    out = {k: [] for k in graph}
    for key, deps in graph.items():
        for dep in deps:
            out[dep].append(key)
    import heapq
    ready = [k for k, d in indegree.items() if d == 0]
    heapq.heapify(ready)
    ordered = []
    while ready:
        key = heapq.heappop(ready)
        ordered.append(key)
        for nxt in sorted(out[key]):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                heapq.heappush(ready, nxt)
    if len(ordered) != len(graph):
        raise ContractError('cyclic dependency graph')
    return ordered

def reachable(edges: dict[str, list[str]], origin: str, *, ceiling: int=20000) -> set[str]:
    graph = normalize(edges)
    if origin not in graph:
        raise ContractError('unknown graph origin')
    queue = deque([origin])
    visited = {origin}
    while queue:
        for nxt in graph[queue.popleft()]:
            if nxt not in visited:
                visited.add(nxt)
                queue.append(nxt)
                if len(visited) > ceiling:
                    raise ContractError('reachability ceiling exceeded')
    return visited
