"""Deterministic finite software-bill-of-materials dependency projection.

All supplier declarations and licenses are *external unreviewed assertions*.
No package is installed, downloaded, executed, scanned for vulnerabilities,
deemed safe, approved for training or accepted as a license entitlement.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections import Counter, deque
import hashlib
import json
import re

from .research_projection import ResearchFormatError, ResearchProjection, project_lines

_SAFE_LABEL = re.compile(r"^[^\x00-\x1f\x7f]{1,256}$")
_ID = re.compile(r"^[A-Za-z0-9._:+/@#-]{1,256}$")
_VERSION = re.compile(r"^[^\x00-\x1f\x7f]{0,128}$")
_LICENSE = re.compile(r"^[A-Za-z0-9._+-]{1,128}$")
_MAX_NODES = 512
_MAX_EDGES = 2048


@dataclass(frozen=True)
class SBOMComponent:
    identity: str
    name: str
    version: str
    declared_license: str = "NOASSERTION"
    ecosystem: str = "unspecified"
    hash_present: bool = False

    def __post_init__(self):
        if not isinstance(self.identity, str) or not _ID.fullmatch(self.identity):
            raise ResearchFormatError("invalid SBOM component identity")
        if not isinstance(self.name, str) or not _SAFE_LABEL.fullmatch(self.name):
            raise ResearchFormatError("invalid SBOM component name")
        if not isinstance(self.version, str) or not _VERSION.fullmatch(self.version):
            raise ResearchFormatError("invalid SBOM component version")
        if not isinstance(self.declared_license, str) or not (
            self.declared_license == "NOASSERTION" or
            _LICENSE.fullmatch(self.declared_license)
        ):
            raise ResearchFormatError("invalid SBOM license identifier")
        if not isinstance(self.ecosystem, str) or not _LICENSE.fullmatch(self.ecosystem):
            raise ResearchFormatError("invalid SBOM ecosystem label")
        if type(self.hash_present) is not bool:
            raise ResearchFormatError("invalid SBOM hash observation")


@dataclass(frozen=True)
class SBOMEdge:
    source: str
    target: str
    relation: str = "depends_on"

    def __post_init__(self):
        if (not isinstance(self.source, str) or not isinstance(self.target, str)
                or not _ID.fullmatch(self.source) or not _ID.fullmatch(self.target)
                or self.relation != "depends_on"):
            raise ResearchFormatError("invalid SBOM dependency edge")


@dataclass(frozen=True)
class SBOMGraph:
    components: tuple[SBOMComponent, ...]
    dependencies: tuple[SBOMEdge, ...]
    unresolved_references: tuple[str, ...]
    roots: tuple[str, ...]
    cyclic_nodes: int
    highest_outdegree: int
    license_unknown: int
    hashes_declared: int
    graph_digest: str
    statements_verified: bool = False
    training_permission: bool = False


def _digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    ).hexdigest()


def make_sbom_graph(
    components: list[SBOMComponent], edges: list[SBOMEdge],
    *, max_components: int = _MAX_NODES, max_edges: int = _MAX_EDGES,
) -> SBOMGraph:
    if (type(max_components) is not int or not 1 <= max_components <= _MAX_NODES
            or type(max_edges) is not int or not 1 <= max_edges <= _MAX_EDGES
            or not isinstance(components, list) or not isinstance(edges, list)
            or not 1 <= len(components) <= max_components
            or len(edges) > max_edges):
        raise ResearchFormatError("SBOM graph capacity exceeded")
    if any(not isinstance(x, SBOMComponent) for x in components):
        raise ResearchFormatError("invalid SBOM graph component")
    if any(not isinstance(x, SBOMEdge) for x in edges):
        raise ResearchFormatError("invalid SBOM graph edge")
    by_id={}
    for node in components:
        if node.identity in by_id:
            raise ResearchFormatError("duplicate SBOM component identity")
        by_id[node.identity]=node
    adj={identity:set() for identity in by_id}
    indegree={identity:0 for identity in by_id}
    unresolved=set()
    edges_seen=set()
    for edge in edges:
        if edge.source not in by_id or edge.target not in by_id:
            if edge.source not in by_id:
                unresolved.add(edge.source)
            if edge.target not in by_id:
                unresolved.add(edge.target)
            continue
        if edge.source==edge.target:
            raise ResearchFormatError("self-referential SBOM dependency")
        pair=(edge.source,edge.target)
        if pair in edges_seen:
            raise ResearchFormatError("duplicate dependency edge")
        edges_seen.add(pair)
        adj[edge.source].add(edge.target)
        indegree[edge.target]+=1
    roots=tuple(sorted(x for x,degree in indegree.items() if degree==0))
    # Kahn removal measures nodes participating in cycles or downstream from
    # cycles. It is an advisory topology signal, not a security verdict.
    pending=dict(indegree)
    queue=deque(roots)
    removed=0
    while queue:
        current=queue.popleft()
        removed+=1
        for target in sorted(adj[current]):
            pending[target]-=1
            if pending[target]==0:
                queue.append(target)
    nodes=tuple(sorted(components,key=lambda x:x.identity))
    arcs=tuple(sorted((a,b) for a,b in edges_seen))
    data={
        "nodes":[{
            "id":x.identity,"name":x.name,"version":x.version,
            "license":x.declared_license,"ecosystem":x.ecosystem,
            "hash_present":x.hash_present,
        } for x in nodes],
        "edges":arcs,"unresolved":sorted(unresolved),
        "roots":roots,"cyclic_or_blocked":len(nodes)-removed,
    }
    return SBOMGraph(
        components=nodes,
        dependencies=tuple(SBOMEdge(a,b) for a,b in arcs),
        unresolved_references=tuple(sorted(unresolved)),
        roots=roots,
        cyclic_nodes=len(nodes)-removed,
        highest_outdegree=max(map(len,adj.values()),default=0),
        license_unknown=sum(x.declared_license=="NOASSERTION" for x in nodes),
        hashes_declared=sum(x.hash_present for x in nodes),
        graph_digest=_digest(data),
    )


def project_sbom(
    graph: SBOMGraph, *, kind: str, max_chars: int, max_items: int = 128,
) -> ResearchProjection:
    if (not isinstance(graph, SBOMGraph) or not isinstance(kind, str)
            or not 1 <= len(kind) <= 128 or type(max_items) is not int
            or not 1 <= max_items <= _MAX_NODES):
        raise ResearchFormatError("invalid SBOM text projection")
    from .sbom_topology import inspect_sbom_topology
    topology = inspect_sbom_topology(graph)
    lines=[
        f"External software inventory: {kind} (unreviewed, not verified)",
        f"Components: {len(graph.components)}; dependencies: {len(graph.dependencies)}",
        f"Roots: {len(graph.roots)}; unresolved references: {len(graph.unresolved_references)}",
        f"Cycle-affected or cyclic nodes: {graph.cyclic_nodes}",
        f"Max declared dependency outdegree: {graph.highest_outdegree}",
        f"True cycle member nodes: {topology.truly_cyclic_nodes}; "
        f"cycle strongly-connected groups: {topology.cyclic_strong_components}",
        f"Longest finite dependency component chain: {topology.longest_condensed_chain}",
        f"Maximum transitive dependencies: {topology.maximum_transitive_dependencies}",
        f"Maximum reverse dependency impact: {topology.maximum_reverse_impact}",
        f"Source roots reachable components: {topology.root_reachable_nodes}",
        f"Dependency topology fingerprint SHA256: {topology.topology_digest}",
        f"License fields missing: {graph.license_unknown}",
        f"Artifact checksum declarations: {graph.hashes_declared}",
        f"Graph fingerprint SHA256: {graph.graph_digest}",
        "Supplier attestations: not verified; no license or vulnerability clearance",
    ]
    for idx,component in enumerate(graph.components[:max_items],1):
        # Component IDs, PURLs, opaque external URLs and hashes are not
        # projected. Names/versions are unreviewed labels only.
        lines.append(
            f"Component {idx}: name: {component.name}; version: "
            f"{component.version or '[unspecified]'}; ecosystem: {component.ecosystem}; "
            f"claimed_license: {component.declared_license}; "
            f"checksum_record_present: {component.hash_present}",
        )
    if len(graph.components)>max_items:
        lines.append(f"Other components omitted by projection cap: {len(graph.components)-max_items}")
    return project_lines(lines,title=f"{kind} software inventory",max_chars=max_chars)
