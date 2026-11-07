"""Bounded inert XML admission for articulated robot/world scene sources."""
from __future__ import annotations

import hashlib
import math
import re
import xml.etree.ElementTree as ET

from .research_projection import ResearchFormatError,check_text
from .scene_topology import SceneNode,SceneEdge,analyze_scene_topology

_FORBIDDEN=re.compile(r"<!\s*(?:DOCTYPE|ENTITY)\b",re.I)
_NAME=re.compile(r"^[A-Za-z_][A-Za-z0-9_./:-]{0,127}$")
_MAX_BYTES=1_048_576


def source_tree(raw:str,*,max_chars:int,root_tag:str)->ET.Element:
    check_text(raw,max_chars=max_chars,max_links=0)
    if _FORBIDDEN.search(raw) or len(raw.encode("utf-8"))>_MAX_BYTES:
        raise ResearchFormatError("robot source contains DTD/entity or exceeds byte bound")
    try:
        root=ET.fromstring(raw)
    except (ET.ParseError,RecursionError) as exc:
        raise ResearchFormatError("malformed articulated scene XML") from exc
    if root.tag!=root_tag:
        raise ResearchFormatError("unapproved articulated source root or namespace")
    elements=0
    stack=[(root,1)]
    while stack:
        node,depth=stack.pop()
        elements+=1
        if elements>16384 or depth>32 or len(node.attrib)>64:
            raise ResearchFormatError("robot XML element/depth/attribute count exceeded")
        for key,value in node.attrib.items():
            if (not isinstance(key,str) or not isinstance(value,str)
                    or len(key)>128 or len(value)>4096):
                raise ResearchFormatError("robot source attribute length exceeded")
        stack.extend((child,depth+1) for child in node)
    return root


def exact_name(value:object)->str:
    if not isinstance(value,str) or not _NAME.fullmatch(value):
        raise ResearchFormatError("robot link/joint identity exceeds finite syntax")
    return value


def finite_number(value:object,*,minval:float=-1e9,maxval:float=1e9)->float:
    if not isinstance(value,str) or len(value)>64:
        raise ResearchFormatError("robot numeric attribute malformed")
    try:
        number=float(value)
    except ValueError as exc:
        raise ResearchFormatError("robot numeric attribute not parsable") from exc
    if not math.isfinite(number) or not minval<=number<=maxval:
        raise ResearchFormatError("robot numeric source outside finite range")
    return number


def topology_for_links(
    source:str,names:list[str],joints:list[tuple[str,str]],
):
    if len(names)>512 or len(joints)>1024 or not names:
        raise ResearchFormatError("articulated graph node/joint capacity invalid")
    known=set(names)
    if len(known)!=len(names):
        raise ResearchFormatError("duplicated articulated link name")
    def encoded(name:str)->str:
        return "link_"+hashlib.sha256(name.encode()).hexdigest()[:24]
    nodes=[SceneNode(encoded(name),"Link","Robot link") for name in names]
    edges=[]
    for parent,child in joints:
        if parent not in known or child not in known:
            raise ResearchFormatError("articulated joint references missing link")
        edges.append(SceneEdge(encoded(parent),encoded(child)))
    return analyze_scene_topology(
        source,nodes,edges,max_nodes=512,max_edges=1024,
    )
