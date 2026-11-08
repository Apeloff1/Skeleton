"""Unity YAML Transform containment observations without YAML object construction.

Only the local m_Father fileID field in Transform/RectTransform records is
read. An unknown parent becomes an explicit unresolved external reference,
never a filesystem/prefab import or a fabricated edge. All node identities
remain untrusted source declarations and no MonoBehaviour is executed.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import re

from .research_projection import ResearchFormatError
from .scene_topology import SceneNode,SceneEdge,SceneTopology,analyze_scene_topology

_HEADER=re.compile(r"^--- !u!(\d{1,5}) &(-?\d{1,20})$")
_FATHER=re.compile(r"^\s*m_Father:\s*\{\s*fileID:\s*(-?\d{1,20})\s*\}\s*$")
_TYPE=frozenset({"4","224"})


@dataclass(frozen=True)
class UnityHierarchy:
    topology:SceneTopology
    transform_count:int
    unresolved_parent_count:int
    duplicate_identity_denied:bool=True
    prefab_loaded:bool=False


def _id(identity:str)->str:
    return "unity_"+hashlib.sha256(identity.encode()).hexdigest()[:24]


def inspect_unity_hierarchy(raw:str)->UnityHierarchy|None:
    if not isinstance(raw,str) or len(raw)>2_097_152:
        raise ResearchFormatError("unbounded Unity serialized scene source")
    rows=raw.splitlines()
    if len(rows)>32768 or not rows or rows[0].strip()!="%YAML 1.1":
        raise ResearchFormatError("Unity scene YAML magic invalid")
    records=[]
    kind=None
    identity=None
    parent=None
    seen=set()
    def flush():
        if kind in _TYPE and identity is not None:
            records.append((identity,kind,parent))
    for row in rows[1:]:
        if len(row)>8192:
            raise ResearchFormatError("Unity hierarchy row too long")
        match=_HEADER.fullmatch(row.strip())
        if match:
            flush()
            kind,identity=match.groups()
            if identity in seen:
                raise ResearchFormatError("duplicate Unity serialized fileID")
            seen.add(identity)
            parent=None
            continue
        if row.strip().startswith("---") and match is None:
            raise ResearchFormatError("malformed Unity YAML document boundary")
        if kind in _TYPE:
            link=_FATHER.fullmatch(row)
            if link:
                if parent is not None:
                    raise ResearchFormatError("duplicate Unity parent annotation")
                parent=link.group(1)
    flush()
    if not records:
        return None
    if len(records)>4096:
        raise ResearchFormatError("Unity transform source capacity exceeded")
    local={identity for identity,_,_ in records}
    nodes=[]
    edges=[]
    unknown=0
    for identity,kind,parent in records:
        label="Transform" if kind=="4" else "RectTransform"
        nodes.append(SceneNode(_id(identity),label,label))
        if parent is None or parent=="0":
            continue
        if parent==identity:
            raise ResearchFormatError("Unity Transform self-parent reference")
        if parent not in local:
            unknown+=1
            continue
        edges.append(SceneEdge(_id(parent),_id(identity)))
    return UnityHierarchy(
        topology=analyze_scene_topology("Unity",nodes,edges,max_nodes=4096),
        transform_count=len(records),
        unresolved_parent_count=unknown,
    )
