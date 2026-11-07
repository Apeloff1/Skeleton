"""Inert finite GraphML node/edge source extraction; no resource resolution."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from .research_projection import ResearchFormatError,ResearchProjection,check_text
from .graph_topology import GraphStatement,inspect_graph_statement,project_graph_topology

GRAPHML_TYPES=frozenset({"application/graphml+xml","application/x-graphml+xml"})
_NS="http://graphml.graphdrawing.org/xmlns"
_FORBIDDEN=re.compile(r"<!\s*(?:DOCTYPE|ENTITY)\b",re.I)


def _tag(value:str)->str:
    return value.rsplit("}",1)[-1] if "}" in value else value


def extract_graphml(
    raw:str,*,max_chars:int=524288,max_links:int=0,
)->ResearchProjection:
    check_text(raw,max_chars=max_chars,max_links=max_links)
    if _FORBIDDEN.search(raw) or len(raw.encode("utf-8"))>1_048_576:
        raise ResearchFormatError("GraphML XML contains forbidden entity or exceeds size")
    try:
        root=ET.fromstring(raw)
    except (ET.ParseError,RecursionError) as exc:
        raise ResearchFormatError("malformed GraphML source") from exc
    if root.tag!=f"{{{_NS}}}graphml":
        raise ResearchFormatError("GraphML root namespace invalid")
    count=0
    selected=[]
    stack=[(root,1)]
    while stack:
        node,depth=stack.pop()
        count+=1
        if count>16384 or depth>32:
            raise ResearchFormatError("GraphML XML element/depth cap exceeded")
        if node.tag==f"{{{_NS}}}graph":
            selected.append(node)
        stack.extend((child,depth+1) for child in node)
    if len(selected)!=1 or selected[0] not in list(root):
        raise ResearchFormatError("GraphML source must contain one root-level graph")
    graph=selected[0]
    default=graph.get("edgedefault")
    if default not in ("directed","undirected"):
        raise ResearchFormatError("GraphML directedness must be explicit")
    directed=default=="directed"
    nodes=[]
    edges=[]
    for entry in graph:
        if entry.tag==f"{{{_NS}}}node":
            identity=entry.get("id")
            if not isinstance(identity,str) or not 1<=len(identity)<=256:
                raise ResearchFormatError("GraphML node identity invalid")
            nodes.append(identity)
            if len(nodes)>512:
                raise ResearchFormatError("GraphML node capacity exceeded")
        elif entry.tag==f"{{{_NS}}}edge":
            source,target=entry.get("source"),entry.get("target")
            if not isinstance(source,str) or not isinstance(target,str):
                raise ResearchFormatError("GraphML edge source/target missing")
            edges.append((source,target))
            if len(edges)>1024:
                raise ResearchFormatError("GraphML edge capacity exceeded")
        elif _tag(entry.tag) in ("hyperedge","port"):
            raise ResearchFormatError("GraphML hyperedge or port not admitted")
        # Data and key text are untrusted and deliberately not retained.
    topology=inspect_graph_statement(GraphStatement(
        tuple(nodes),tuple(edges),directed,"GraphML",
    ))
    return project_graph_topology(topology,max_chars=max_chars)
