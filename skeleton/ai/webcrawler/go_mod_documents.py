"""Conservative Go module requirement graph, not a Go parser or module loader."""
from __future__ import annotations

import re
from .sbom_graph import SBOMComponent, SBOMEdge, make_sbom_graph, project_sbom
from .research_projection import ResearchFormatError, ResearchProjection, check_text

GO_MOD_TYPES=frozenset({"text/x-go-mod","application/x-go-mod"})
_MODULE=re.compile(r"^[A-Za-z0-9._~+/!-]{1,256}$")
_VERSION=re.compile(r"^v[0-9][A-Za-z0-9.+_-]{0,127}$")

def extract_go_mod(
    raw:str,*,max_chars:int=524288,max_links:int=0,
)->ResearchProjection:
    check_text(raw,max_chars=max_chars,max_links=max_links)
    lines=raw.lstrip("\ufeff").splitlines()
    if not 1<=len(lines)<=8192:
        raise ResearchFormatError("Go module row capacity exceeded")
    root=None
    group=False
    requirements={}
    for source in lines:
        if len(source)>8192:
            raise ResearchFormatError("Go module line width exceeded")
        row=source.split("//",1)[0].strip()
        if not row:
            continue
        if row.startswith("module "):
            if root is not None or not _MODULE.fullmatch(row[7:].strip()):
                raise ResearchFormatError("duplicate or invalid module root")
            root=row[7:].strip()
            continue
        if row=="require (":
            if group:
                raise ResearchFormatError("nested Go requirement block")
            group=True
            continue
        if row==")":
            if not group:
                raise ResearchFormatError("unexpected Go module group terminator")
            group=False
            continue
        if row.startswith("require ") and not group:
            parts=row[8:].split()
        elif group:
            parts=row.split()
        else:
            # replace, toolchain and exclude are never interpreted as IO.
            continue
        if len(parts)!=2 or not _MODULE.fullmatch(parts[0]) or not _VERSION.fullmatch(parts[1]):
            raise ResearchFormatError("malformed Go requirement")
        if parts[0] in requirements and requirements[parts[0]]!=parts[1]:
            raise ResearchFormatError("conflicting Go source requirements")
        requirements[parts[0]]=parts[1]
        if len(requirements)>256:
            raise ResearchFormatError("Go dependency count exceeded")
    if root is None or group or not requirements:
        raise ResearchFormatError("incomplete Go module inventory")
    nodes=[SBOMComponent("go_root","Go module source root","",ecosystem="go")]
    edges=[]
    for i,(name,version) in enumerate(sorted(requirements.items()),1):
        sid=f"go_req_{i}"
        nodes.append(SBOMComponent(sid,name,version,ecosystem="go"))
        edges.append(SBOMEdge("go_root",sid))
    return project_sbom(make_sbom_graph(nodes,edges),
                        kind="Go module",max_chars=max_chars)
