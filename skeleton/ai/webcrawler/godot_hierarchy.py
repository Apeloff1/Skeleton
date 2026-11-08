"""Reconstruct Godot 4 text-scene node containment without loading resources.

The source Godot .tscn parent="." is its document root. Other parent
paths are relative slash-separated scene node paths; no filesystem paths,
scripts, imports, parent traversal or external resource loads are allowed.
"""
from __future__ import annotations

import hashlib
import re

from .research_projection import ResearchFormatError
from .scene_topology import SceneNode,SceneEdge,SceneTopology,analyze_scene_topology

_NODE=re.compile(
    r'^\[node\s+name="([A-Za-z0-9_ .-]{1,128})"'
    r'\s+type="([A-Za-z0-9_]{1,96})"([^\]\r\n]{0,512})\]$'
)
_PARENT=re.compile(r'\bparent="([A-Za-z0-9_ ./-]{1,256})"')
_SEGMENT=re.compile(r"^[A-Za-z0-9_ .-]{1,128}$")


def _node_id(path:str)->str:
    return "root" if path=="." else "node_"+hashlib.sha256(path.encode()).hexdigest()[:24]


def _parent_path(raw:str)->str:
    value=raw.strip()
    if not value or value=="/":
        raise ResearchFormatError("Godot scene parent path empty or rooted")
    if value==".":
        return "."
    parts=value.split("/")
    if any(not _SEGMENT.fullmatch(part) or part in (".","..") for part in parts):
        raise ResearchFormatError("Godot scene parent escapes document hierarchy")
    return "/".join(parts)


def inspect_godot_hierarchy(raw:str)->SceneTopology:
    if not isinstance(raw,str) or len(raw)>2_097_152:
        raise ResearchFormatError("unbounded Godot scene topology source")
    descriptions=[]
    root_count=0
    used_paths=set()
    for line in raw.splitlines():
        match=_NODE.fullmatch(line.strip())
        if not match:
            continue
        name,kind,attr=match.groups()
        if name in (".","..") or "/" in name:
            raise ResearchFormatError("Godot node identity has path traversal")
        parent_match=_PARENT.search(attr)
        if parent_match:
            parent=_parent_path(parent_match.group(1))
            full_path=name if parent=="." else parent+"/"+name
        else:
            root_count+=1
            if root_count>1:
                raise ResearchFormatError("Godot scene has multiple unnamed roots")
            parent=None
            full_path="."
        if full_path in used_paths:
            raise ResearchFormatError("Godot scene node path duplicated")
        used_paths.add(full_path)
        descriptions.append((full_path,name,kind,parent))
        if len(descriptions)>2048:
            raise ResearchFormatError("Godot scene node hierarchy capacity exceeded")
    if not descriptions or root_count!=1:
        raise ResearchFormatError("Godot source lacks a single root")
    paths={part[0] for part in descriptions}
    nodes=[]
    edges=[]
    for path,name,kind,parent in descriptions:
        nodes.append(SceneNode(_node_id(path),kind,name))
        if parent is None:
            continue
        if parent not in paths:
            raise ResearchFormatError("Godot parent node does not exist")
        edges.append(SceneEdge(_node_id(parent),_node_id(path)))
    return analyze_scene_topology("Godot",nodes,edges,max_nodes=2048,max_edges=4096)
