"""Bounded GEXF 1.2/1.3 graph topology, not a network graph service."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from .research_projection import ResearchFormatError,ResearchProjection,check_text
from .graph_topology import GraphStatement,inspect_graph_statement,project_graph_topology

GEXF_TYPES=frozenset({"application/gexf+xml","application/x-gexf+xml"})
_NS=frozenset({"http://www.gexf.net/1.2draft","http://gexf.net/1.3"})
_FORBIDDEN=re.compile(r"<!\s*(?:DOCTYPE|ENTITY)\b",re.I)


def _parts(tag:str)->tuple[str,str]:
    if tag.startswith("{"):
        return tuple(tag[1:].split("}",1))
    return "",tag


def extract_gexf(
    raw:str,*,max_chars:int=524288,max_links:int=0,
)->ResearchProjection:
    check_text(raw,max_chars=max_chars,max_links=max_links)
    if _FORBIDDEN.search(raw) or len(raw.encode("utf-8"))>1_048_576:
        raise ResearchFormatError("GEXF XML entities or size out of bounds")
    try:
        root=ET.fromstring(raw)
    except (ET.ParseError,RecursionError) as exc:
        raise ResearchFormatError("invalid GEXF XML") from exc
    namespace,kind=_parts(root.tag)
    if kind!="gexf" or namespace not in _NS:
        raise ResearchFormatError("unsupported GEXF namespace or root")
    graphs=[entry for entry in root if _parts(entry.tag)==(namespace,"graph")]
    if len(graphs)!=1:
        raise ResearchFormatError("GEXF requires exactly one declared graph")
    graph=graphs[0]
    edge_type=graph.get("defaultedgetype")
    if edge_type not in ("directed","undirected"):
        raise ResearchFormatError("GEXF directedness missing or invalid")
    count=0
    stack=[(root,1)]
    while stack:
        node,depth=stack.pop()
        count+=1
        if count>16384 or depth>32:
            raise ResearchFormatError("GEXF element/depth count exceeded")
        stack.extend((child,depth+1) for child in node)
    nodes=[]
    edges=[]
    for part in graph:
        _,section=_parts(part.tag)
        if section=="nodes":
            if len(nodes):
                raise ResearchFormatError("duplicate GEXF nodes section")
            for row in part:
                if _parts(row.tag)!=(namespace,"node"):
                    raise ResearchFormatError("GEXF node child invalid")
                identity=row.get("id")
                if not isinstance(identity,str) or not 1<=len(identity)<=256:
                    raise ResearchFormatError("invalid GEXF node ID")
                nodes.append(identity)
                if len(nodes)>512:
                    raise ResearchFormatError("GEXF node limit exceeded")
        elif section=="edges":
            if len(edges):
                raise ResearchFormatError("duplicate GEXF edges section")
            for row in part:
                if _parts(row.tag)!=(namespace,"edge"):
                    raise ResearchFormatError("GEXF edge child invalid")
                source,target=row.get("source"),row.get("target")
                if not isinstance(source,str) or not isinstance(target,str):
                    raise ResearchFormatError("GEXF edge identity invalid")
                edges.append((source,target))
                if len(edges)>1024:
                    raise ResearchFormatError("GEXF edge count exceeded")
        # Viz extensions, node attributes, URIs, dynamics and labels
        # remain inert and do not lead to network requests.
    topology=inspect_graph_statement(GraphStatement(
        tuple(nodes),tuple(edges),edge_type=="directed","GEXF",
    ))
    return project_graph_topology(topology,max_chars=max_chars)
