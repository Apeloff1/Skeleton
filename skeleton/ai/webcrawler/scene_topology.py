"""Deterministic bounded engine-neutral scene containment topology.

Scene nodes and edges are *untrusted source declarations*, not instantiated
game objects. They are never applied to a live world, loaded into a renderer,
granted disk access, or treated as executable build instructions.
"""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
import hashlib
import json
import re

from .research_projection import ResearchFormatError

_ID=re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_CLASS=re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,95}$")
_MAX_NODES=4096
_MAX_EDGES=8192


@dataclass(frozen=True)
class SceneNode:
    node_id:str
    kind:str
    label:str
    declared_resources:int=0
    unverified:bool=True

    def __post_init__(self):
        if not isinstance(self.node_id,str) or not _ID.fullmatch(self.node_id):
            raise ResearchFormatError("invalid scene graph node identity")
        if not isinstance(self.kind,str) or not _CLASS.fullmatch(self.kind):
            raise ResearchFormatError("invalid scene graph node type")
        if (not isinstance(self.label,str) or not 1<=len(self.label)<=128
                or any(ord(char)<32 or ord(char)==127 for char in self.label)):
            raise ResearchFormatError("invalid scene graph label")
        if type(self.declared_resources) is not int or not 0<=self.declared_resources<=256:
            raise ResearchFormatError("invalid scene declared resource count")


@dataclass(frozen=True)
class SceneEdge:
    parent_id:str
    child_id:str
    kind:str="contains"

    def __post_init__(self):
        if (not isinstance(self.parent_id,str) or not _ID.fullmatch(self.parent_id)
                or not isinstance(self.child_id,str) or not _ID.fullmatch(self.child_id)
                or self.kind!="contains" or self.parent_id==self.child_id):
            raise ResearchFormatError("invalid scene hierarchy edge")


@dataclass(frozen=True)
class SceneTopology:
    engine:str
    node_count:int
    edge_count:int
    root_count:int
    leaf_count:int
    maximum_depth:int
    maximum_children:int
    isolated_nodes:int
    type_counts:tuple[tuple[str,int],...]
    canonical_digest:str
    untrusted_external_source:bool=True
    renderer_executed:bool=False
    imports_loaded:bool=False
    game_build_authorized:bool=False


def _digest(payload:object)->str:
    return hashlib.sha256(
        json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    ).hexdigest()


def analyze_scene_topology(
    engine:str,nodes:list[SceneNode],edges:list[SceneEdge],
    *,max_nodes:int=_MAX_NODES,max_edges:int=_MAX_EDGES,
)->SceneTopology:
    if (not isinstance(engine,str) or not _CLASS.fullmatch(engine)
            or not isinstance(nodes,list) or not isinstance(edges,list)
            or type(max_nodes) is not int or not 1<=max_nodes<=_MAX_NODES
            or type(max_edges) is not int or not 0<=max_edges<=_MAX_EDGES
            or not 1<=len(nodes)<=max_nodes or len(edges)>max_edges):
        raise ResearchFormatError("invalid scene graph capacity or engine")
    if any(not isinstance(x,SceneNode) for x in nodes):
        raise ResearchFormatError("scene graph has non-node entries")
    if any(not isinstance(x,SceneEdge) for x in edges):
        raise ResearchFormatError("scene graph has non-containment edges")
    index={node.node_id:i for i,node in enumerate(nodes)}
    if len(index)!=len(nodes):
        raise ResearchFormatError("duplicate source scene identity")
    adj=[set() for _ in nodes]
    indegrees=[0]*len(nodes)
    edge_ids=set()
    for edge in edges:
        if edge.parent_id not in index or edge.child_id not in index:
            raise ResearchFormatError("scene child parent is absent from source")
        a,b=index[edge.parent_id],index[edge.child_id]
        if (a,b) in edge_ids:
            raise ResearchFormatError("duplicate scene edge")
        edge_ids.add((a,b))
        if indegrees[b]:
            raise ResearchFormatError("scene tree node has multiple parents")
        indegrees[b]+=1
        adj[a].add(b)
    roots=[i for i,num in enumerate(indegrees) if num==0]
    if not roots:
        raise ResearchFormatError("scene graph has no roots")
    pending=indegrees[:]
    queue=deque(sorted(roots,key=lambda i:nodes[i].node_id))
    depths=[0]*len(nodes)
    traversed=0
    while queue:
        parent=queue.popleft()
        traversed+=1
        for child in sorted(adj[parent],key=lambda i:nodes[i].node_id):
            depths[child]=max(depths[child],depths[parent]+1)
            pending[child]-=1
            if pending[child]==0:
                queue.append(child)
    if traversed!=len(nodes):
        raise ResearchFormatError("scene containment graph contains a cycle")
    kinds=Counter(node.kind for node in nodes)
    payload={
        "engine":engine,
        "nodes":[(x.node_id,x.kind,x.label,x.declared_resources)
                 for x in sorted(nodes,key=lambda node:node.node_id)],
        "edges":sorted((x.parent_id,x.child_id) for x in edges),
        "roots":sorted(nodes[i].node_id for i in roots),
        "depth":max(depths),
    }
    return SceneTopology(
        engine=engine,node_count=len(nodes),edge_count=len(edges),
        root_count=len(roots),
        leaf_count=sum(not children for children in adj),
        maximum_depth=max(depths),
        maximum_children=max(map(len,adj),default=0),
        isolated_nodes=sum(not adj[i] and indegrees[i]==0 for i in range(len(nodes))),
        type_counts=tuple(sorted(kinds.items())),
        canonical_digest=_digest(payload),
    )


def summarize_scene_topology(topology:SceneTopology)->tuple[str,...]:
    if not isinstance(topology,SceneTopology):
        raise ResearchFormatError("typed scene graph required")
    return (
        f"Scene topology engine: {topology.engine}",
        f"Hierarchy: nodes={topology.node_count}; edges={topology.edge_count}; "
        f"roots={topology.root_count}; leaves={topology.leaf_count}",
        f"Hierarchy depth: {topology.maximum_depth}; "
        f"max child fanout: {topology.maximum_children}; "
        f"isolated: {topology.isolated_nodes}",
        f"Scene topology SHA256: {topology.canonical_digest}",
        "Source scene hierarchy not instantiated, reviewed or approved",
    )
