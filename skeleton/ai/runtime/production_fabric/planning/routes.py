"""Deterministic weighted routes with explicit obstacles and tie-stable Dijkstra."""
from heapq import heappush, heappop
from ..contracts.errors import ContractError

def shortest(graph: dict[str, dict[str, int]], origin: str, target: str, *, blocked: set[str] | None=None, max_nodes: int=50000) -> dict | None:
    if not isinstance(graph, dict) or len(graph) > max_nodes or origin not in graph or (target not in graph):
        raise ContractError('invalid route graph')
    blocked = blocked or set()
    if origin in blocked or target in blocked:
        return None
    for node, refs in graph.items():
        if not isinstance(refs, dict) or any((dest not in graph or type(cost) is not int or (not 1 <= cost <= 100000) for dest, cost in refs.items())):
            raise ContractError('invalid weighted route')
    queue = [(0, (origin,), origin)]
    best = {origin: (0, (origin,))}
    while queue:
        cost, path, node = heappop(queue)
        if best.get(node) != (cost, path):
            continue
        if node == target:
            return {'path': list(path), 'cost': cost, 'visited': len(best)}
        for dest, edge in sorted(graph[node].items()):
            if dest in blocked:
                continue
            proposal = (cost + edge, path + (dest,))
            if dest not in best or proposal < best[dest]:
                best[dest] = proposal
                heappush(queue, (proposal[0], proposal[1], dest))
    return None
