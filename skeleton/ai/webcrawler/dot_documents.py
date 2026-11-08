"""Strict bounded DOT edge-list subset; no Graphviz invocation or asset loads.

Only named directed or undirected graphs with simple node/edge statements
are admitted. HTML node labels, URLs, attributes, subgraphs, comments,
layout directives, filesystem references and scriptable extensions are
not interpreted. This is not a full DOT language parser.
"""
from __future__ import annotations

import re

from .research_projection import ResearchFormatError,ResearchProjection,check_text
from .graph_topology import GraphStatement,inspect_graph_statement,project_graph_topology

DOT_TYPES=frozenset({"text/vnd.graphviz","text/x-dot"})
_HEADER=re.compile(r"^\s*(strict\s+)?(digraph|graph)\s*(?:[A-Za-z_][A-Za-z0-9_]{0,100}\s*)?\{\s*$")
_IDENT=r"([A-Za-z_][A-Za-z0-9_]{0,100})"
_NODE=re.compile(r"^\s*"+_IDENT+r"\s*;\s*$")
_DIRECTED=re.compile(r"^\s*"+_IDENT+r"\s*->\s*"+_IDENT+r"\s*;\s*$")
_UNDIRECTED=re.compile(r"^\s*"+_IDENT+r"\s*--\s*"+_IDENT+r"\s*;\s*$")


def extract_dot_graph(
    raw:str,*,max_chars:int=524288,max_links:int=0,
)->ResearchProjection:
    check_text(raw,max_chars=max_chars,max_links=max_links)
    lines=raw.lstrip("\ufeff").splitlines()
    if len(lines)<3 or len(lines)>4096:
        raise ResearchFormatError("DOT source line capacity exceeded")
    match=_HEADER.fullmatch(lines[0])
    if match is None:
        raise ResearchFormatError("DOT graph header unsupported")
    directed=match.group(2)=="digraph"
    if lines[-1].strip()!="}":
        raise ResearchFormatError("DOT graph closing brace missing")
    nodes=set()
    edges=[]
    for row in lines[1:-1]:
        if len(row)>2048:
            raise ResearchFormatError("DOT statement too long")
        if not row.strip():
            continue
        edge=(_DIRECTED if directed else _UNDIRECTED).fullmatch(row)
        if edge:
            a,b=edge.groups()
            nodes.update((a,b))
            edges.append((a,b))
            if len(edges)>1024 or len(nodes)>512:
                raise ResearchFormatError("DOT edge/node count exceeded")
            continue
        vertex=_NODE.fullmatch(row)
        if vertex:
            nodes.add(vertex.group(1))
            if len(nodes)>512:
                raise ResearchFormatError("DOT node count exceeded")
            continue
        raise ResearchFormatError("DOT unsupported attribute, markup or subgraph")
    topology=inspect_graph_statement(GraphStatement(
        tuple(sorted(nodes)),tuple(edges),directed,"DOT graph",
    ))
    return project_graph_topology(topology,max_chars=max_chars)
