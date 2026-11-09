"""Bounded graph-native source topology over untrusted external declarations.

All nodes and arcs are statement-level observations, not established
dependencies, facts, access-control relationships, consent or provenance.
Source-controlled IDs and properties are never exposed in the projection
or treated as network links. Only finite normalized graph topology is kept.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import re

from .research_projection import ResearchFormatError,ResearchProjection,project_lines
from .sbom_graph import SBOMComponent,SBOMEdge,make_sbom_graph
from .sbom_topology import inspect_sbom_topology

_MAX_NODES=512
_MAX_ARCS=2048
_LABEL=re.compile(r"^[^\x00-\x1f\x7f]{1,256}$")


@dataclass(frozen=True)
class GraphStatement:
    node_ids:tuple[str,...]
    edges:tuple[tuple[str,str],...]
    directed:bool
    format_name:str
    source_validated:bool=False
    network_executed:bool=False
    source_rights_granted:bool=False


@dataclass(frozen=True)
class GraphTopology:
    format_name:str
    node_count:int
    edge_count:int
    directed:bool
    self_loops:int
    parallel_edges:int
    isolated_nodes:int
    weakly_connected_components:int
    cyclic_nodes:int
    strongly_connected_cycle_groups:int
    maximum_in_degree:int
    maximum_out_degree:int
    longest_condensed_chain:int
    maximum_reverse_reach:int
    graph_digest:str
    data_verified:bool=False
    network_executed:bool=False


def _hash_id(raw:str)->str:
    return "node_"+hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def inspect_graph_statement(
    statement:GraphStatement,*,max_nodes:int=_MAX_NODES,max_edges:int=_MAX_ARCS,
)->GraphTopology:
    if (not isinstance(statement,GraphStatement)
            or type(statement.directed) is not bool
            or not isinstance(statement.format_name,str)
            or not _LABEL.fullmatch(statement.format_name)
            or not isinstance(statement.node_ids,tuple)
            or not isinstance(statement.edges,tuple)
            or type(max_nodes) is not int or not 1<=max_nodes<=_MAX_NODES
            or type(max_edges) is not int or not 1<=max_edges<=_MAX_ARCS
            or not 1<=len(statement.node_ids)<=max_nodes
            or len(statement.edges)>max_edges):
        raise ResearchFormatError("graph source statement exceeds finite bound")
    ids=statement.node_ids
    if len(set(ids))!=len(ids):
        raise ResearchFormatError("graph source duplicate node identity")
    if any(not isinstance(x,str) or not _LABEL.fullmatch(x) for x in ids):
        raise ResearchFormatError("graph source node label rejected")
    index={value:i for i,value in enumerate(ids)}
    n=len(ids)
    adjacency=[set() for _ in ids]
    incoming=[set() for _ in ids]
    undirected=[set() for _ in ids]
    unique_arcs=set()
    self_loops=parallel=0
    for entry in statement.edges:
        if (not isinstance(entry,tuple) or len(entry)!=2
                or any(not isinstance(x,str) or x not in index for x in entry)):
            raise ResearchFormatError("graph source dangling arc")
        a,b=index[entry[0]],index[entry[1]]
        if a==b:
            self_loops+=1
            continue
        identity=(a,b) if statement.directed else tuple(sorted((a,b)))
        if identity in unique_arcs:
            parallel+=1
            continue
        unique_arcs.add(identity)
        adjacency[a].add(b)
        incoming[b].add(a)
        undirected[a].add(b)
        undirected[b].add(a)
        if not statement.directed:
            adjacency[b].add(a)
            incoming[a].add(b)
    # Every node is traversed once per undirected connected component.
    seen=set()
    connected=0
    for start in range(n):
        if start in seen:
            continue
        connected+=1
        stack=[start]
        seen.add(start)
        while stack:
            node=stack.pop()
            for next_node in sorted(undirected[node]):
                if next_node not in seen:
                    seen.add(next_node)
                    stack.append(next_node)
    # Edge IDs are hashed before running the existing finite SCC kernel.
    # Undirected sources are represented as reciprocal adjacency arcs,
    # so a two-vertex undirected connected pair is strongly connected.
    edges=[
        SBOMEdge(_hash_id(ids[a]),_hash_id(ids[b]))
        for a in range(n) for b in sorted(adjacency[a])
    ]
    graph=make_sbom_graph(
        [SBOMComponent(_hash_id(x),"Source graph node","",ecosystem="graph")
         for x in ids],edges,max_components=max_nodes,max_edges=2048,
    )
    topology=inspect_sbom_topology(graph)
    payload={
        "nodes":sorted(_hash_id(x) for x in ids),
        "edges":sorted((a,b) for a,b in unique_arcs),
        "directed":statement.directed,"loops":self_loops,"parallel":parallel,
        "format":statement.format_name,
    }
    return GraphTopology(
        format_name=statement.format_name,node_count=n,
        edge_count=len(unique_arcs),directed=statement.directed,
        self_loops=self_loops,parallel_edges=parallel,
        isolated_nodes=sum(not undirected[i] for i in range(n)),
        weakly_connected_components=connected,
        cyclic_nodes=min(n,topology.truly_cyclic_nodes+self_loops),
        strongly_connected_cycle_groups=topology.cyclic_strong_components,
        maximum_in_degree=max(map(len,incoming),default=0),
        maximum_out_degree=max(map(len,adjacency),default=0),
        longest_condensed_chain=topology.longest_condensed_chain,
        maximum_reverse_reach=topology.maximum_reverse_impact,
        graph_digest=hashlib.sha256(json.dumps(
            payload,sort_keys=True,separators=(",",":")
        ).encode()).hexdigest(),
    )


def project_graph_topology(
    data:GraphTopology,*,max_chars:int,
)->ResearchProjection:
    if not isinstance(data,GraphTopology):
        raise ResearchFormatError("typed graph projection required")
    lines=[
        f"Graph source format: {data.format_name}; directed: {data.directed}",
        f"Nodes: {data.node_count}; unique arcs: {data.edge_count}",
        f"Self loops: {data.self_loops}; duplicate/parallel arcs: {data.parallel_edges}",
        f"Isolated nodes: {data.isolated_nodes}; "
        f"weak components: {data.weakly_connected_components}",
        f"Graph SCC cycle groups: {data.strongly_connected_cycle_groups}; "
        f"cyclic nodes estimated: {data.cyclic_nodes}",
        f"Maximum in degree: {data.maximum_in_degree}; "
        f"out degree: {data.maximum_out_degree}",
        f"Maximum reverse reach: {data.maximum_reverse_reach}; "
        f"longest SCC chain: {data.longest_condensed_chain}",
        f"Graph structural SHA256: {data.graph_digest}",
        "Source assertions unreviewed; no graph execution or URL traversal",
    ]
    return project_lines(
        lines,title=data.format_name+" graph inventory",max_chars=max_chars,
    )
