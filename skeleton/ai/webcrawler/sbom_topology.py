"""Finite exact dependency topology and impact measurements for SBOM snapshots.

This examines only the already parsed *unreviewed supplier declarations*.
No dependency is installed, verified, vulnerability-scanned, or granted rights.
Strongly connected components distinguish actual cycles from nodes blocked
downstream of a cycle, which a naive topological-removal count conflates.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import hashlib
import json

from .research_projection import ResearchFormatError
from .sbom_graph import SBOMGraph

_MAX_NODES=512
_MAX_EDGES=2048


@dataclass(frozen=True)
class DependencyHotspot:
    component_id: str
    downstream_dependencies: int
    upstream_dependents: int
    direct_dependencies: int
    in_cycle: bool
    review_required: bool=True


@dataclass(frozen=True)
class SBOMTopology:
    source_graph_digest: str
    component_count: int
    dependency_edges: int
    cyclic_strong_components: int
    truly_cyclic_nodes: int
    largest_strong_component: int
    connected_components: int
    longest_condensed_chain: int
    maximum_transitive_dependencies: int
    maximum_reverse_impact: int
    root_reachable_nodes: int
    hotspots: tuple[DependencyHotspot,...]
    topology_digest: str
    independently_verified: bool=False
    network_executed: bool=False


def _walk(start:int, arcs:list[set[int]])->set[int]:
    visited={start}
    stack=[start]
    while stack:
        node=stack.pop()
        for child in sorted(arcs[node]):
            if child not in visited:
                visited.add(child)
                stack.append(child)
    visited.discard(start)
    return visited


def _strong_components(graph:list[set[int]])->tuple[list[list[int]],list[int]]:
    # Iterative Kosaraju. No recursion proportional to attacker data.
    size=len(graph)
    visited=set()
    finish=[]
    for origin in range(size):
        if origin in visited:
            continue
        visited.add(origin)
        stack=[(origin,0,sorted(graph[origin]))]
        while stack:
            node,index,neighbors=stack[-1]
            if index==len(neighbors):
                finish.append(node)
                stack.pop()
                continue
            child=neighbors[index]
            stack[-1]=(node,index+1,neighbors)
            if child not in visited:
                visited.add(child)
                stack.append((child,0,sorted(graph[child])))
    reverse=[set() for _ in range(size)]
    for origin,targets in enumerate(graph):
        for child in targets:
            reverse[child].add(origin)
    belong=[-1]*size
    components=[]
    for origin in reversed(finish):
        if belong[origin]!=-1:
            continue
        group=len(components)
        members=[]
        todo=[origin]
        belong[origin]=group
        while todo:
            node=todo.pop()
            members.append(node)
            for parent in sorted(reverse[node]):
                if belong[parent]==-1:
                    belong[parent]=group
                    todo.append(parent)
        components.append(sorted(members))
    return components,belong


def inspect_sbom_topology(
    source:SBOMGraph, *, max_hotspots:int=8,
)->SBOMTopology:
    if not isinstance(source,SBOMGraph):
        raise ResearchFormatError("typed SBOM graph required")
    if type(max_hotspots) is not int or not 1<=max_hotspots<=32:
        raise ResearchFormatError("SBOM hotspot projection limit invalid")
    nodes=source.components
    arcs=source.dependencies
    if not 1<=len(nodes)<=_MAX_NODES or len(arcs)>_MAX_EDGES:
        raise ResearchFormatError("SBOM topology graph capacity exceeded")
    names=[x.identity for x in nodes]
    if len(set(names))!=len(names):
        raise ResearchFormatError("ambiguous topology nodes")
    index={name:i for i,name in enumerate(names)}
    adjacency=[set() for _ in nodes]
    reverse=[set() for _ in nodes]
    for edge in arcs:
        if edge.source not in index or edge.target not in index:
            raise ResearchFormatError("topology has unrecognized dependency identity")
        a,b=index[edge.source],index[edge.target]
        if a==b or b in adjacency[a]:
            raise ResearchFormatError("topology has self/duplicate edge")
        adjacency[a].add(b)
        reverse[b].add(a)
    groups,belongs=_strong_components(adjacency)
    cyclic={v for group in groups if len(group)>1 for v in group}
    condensed=[set() for _ in groups]
    indegrees=[0]*len(groups)
    for a,targets in enumerate(adjacency):
        for b in targets:
            ga,gb=belongs[a],belongs[b]
            if ga!=gb and gb not in condensed[ga]:
                condensed[ga].add(gb)
                indegrees[gb]+=1
    # Longest path on a DAG of SCCs. A cycle does not create unbounded depth.
    pending=indegrees[:]
    queue=deque(i for i,x in enumerate(pending) if x==0)
    levels=[0]*len(groups)
    walked=0
    while queue:
        group=queue.popleft()
        walked+=1
        for child in sorted(condensed[group]):
            levels[child]=max(levels[child],levels[group]+1)
            pending[child]-=1
            if pending[child]==0:
                queue.append(child)
    if walked!=len(groups):
        raise ResearchFormatError("internal SCC condensation not acyclic")
    dependencies=[_walk(i,adjacency) for i in range(len(nodes))]
    dependents=[_walk(i,reverse) for i in range(len(nodes))]
    root_indices=[i for i in range(len(nodes)) if not reverse[i]]
    reachable=set(root_indices)
    for root in root_indices:
        reachable.update(dependencies[root])
    # An absence of indegree-zero nodes may indicate fully cyclic inventory.
    hot=[
        DependencyHotspot(
            component_id=names[i],
            downstream_dependencies=len(dependencies[i]),
            upstream_dependents=len(dependents[i]),
            direct_dependencies=len(adjacency[i]),
            in_cycle=i in cyclic,
        )
        for i in range(len(nodes))
    ]
    hot.sort(key=lambda item:(
        -item.upstream_dependents,-item.downstream_dependencies,
        -item.direct_dependencies,item.component_id,
    ))
    payload={
        "source":source.graph_digest,"scc":[sorted(names[i] for i in part) for part in groups],
        "reaches":sorted((names[i],len(dependencies[i]),len(dependents[i]))
                         for i in range(len(nodes))),
        "max_depth":max(levels,default=0),"roots":sorted(names[i] for i in root_indices),
    }
    return SBOMTopology(
        source_graph_digest=source.graph_digest,
        component_count=len(nodes),dependency_edges=len(arcs),
        cyclic_strong_components=sum(len(g)>1 for g in groups),
        truly_cyclic_nodes=len(cyclic),
        largest_strong_component=max(map(len,groups),default=0),
        connected_components=len(groups),
        longest_condensed_chain=max(levels,default=0),
        maximum_transitive_dependencies=max(map(len,dependencies),default=0),
        maximum_reverse_impact=max(map(len,dependents),default=0),
        root_reachable_nodes=len(reachable),
        hotspots=tuple(hot[:max_hotspots]),
        topology_digest=hashlib.sha256(
            json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
        ).hexdigest(),
    )
