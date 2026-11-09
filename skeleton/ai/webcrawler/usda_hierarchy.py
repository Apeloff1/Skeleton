"""Finite lexical ASCII USD prim containment graph without composition.

Only explicit def/over/class primitive declarations and their brace scope
are interpreted. References, asset URIs, payloads, schemas and composition
arcs are never loaded. This is a syntactic source approximation, not a USD
renderer or full semantic validator.
"""
from __future__ import annotations
import hashlib
import re

from .research_projection import ResearchFormatError
from .scene_topology import SceneNode,SceneEdge,SceneTopology,analyze_scene_topology

_DECL=re.compile(
    r'^\s*(?:def|over|class)\s+([A-Za-z_][A-Za-z0-9_]{0,95})'
    r'\s+"([A-Za-z0-9_ .-]{1,128})"\s*(\{|\{\}|\{ \})\s*$'
)


def _id(path:str)->str:
    return "usd_"+hashlib.sha256(path.encode()).hexdigest()[:24]


def inspect_usda_hierarchy(raw:str)->SceneTopology:
    if not isinstance(raw,str) or len(raw)>2_097_152:
        raise ResearchFormatError("unbounded USD ASCII scene")
    rows=raw.lstrip("\ufeff").splitlines()
    if not rows or rows[0].strip()!="#usda 1.0" or len(rows)>32768:
        raise ResearchFormatError("USD 1.0 header or finite row limit invalid")
    stack:list[str]=[]
    nodes=[]
    edges=[]
    known=set()
    for row in rows[1:]:
        if len(row)>8192:
            raise ResearchFormatError("USD prim source line width exceeded")
        line=row.strip()
        if line=="}":
            if not stack:
                raise ResearchFormatError("USD prim scope closes without declaration")
            stack.pop()
            continue
        match=_DECL.fullmatch(row)
        if match is None:
            # Other USD values are untrusted inert source text. In
            # particular an external @asset@ cannot change the prim tree.
            continue
        kind,name,opening=match.groups()
        if name in (".",".."):
            raise ResearchFormatError("invalid USD prim path segment")
        path="/".join((*stack,name))
        if path in known:
            raise ResearchFormatError("duplicate USD prim path identity")
        known.add(path)
        nodes.append(SceneNode(_id(path),kind,name))
        if stack:
            parent="/".join(stack)
            edges.append(SceneEdge(_id(parent),_id(path)))
        if opening=="{":
            stack.append(name)
            if len(stack)>32:
                raise ResearchFormatError("USD prim nesting exceeds bound")
        if len(nodes)>4096:
            raise ResearchFormatError("USD declared prim count exceeded")
    if stack:
        raise ResearchFormatError("unclosed USD primitive scopes")
    if not nodes:
        raise ResearchFormatError("USD scene contains no finite prim tree")
    return analyze_scene_topology("USD",nodes,edges,max_nodes=4096)
