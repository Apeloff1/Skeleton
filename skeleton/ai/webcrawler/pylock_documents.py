"""Python pylock.toml v1 source graph, no package installer or artifact IO."""
from __future__ import annotations

import tomllib
from .sbom_graph import SBOMComponent, SBOMEdge, make_sbom_graph, project_sbom
from .sbom_parsing import label
from .research_projection import ResearchFormatError, ResearchProjection, check_text

PYLOCK_TYPES=frozenset({"application/vnd.python.pylock+toml","text/x-pylock"})

def extract_pylock(
    raw:str,*,max_chars:int=524288,max_links:int=0,
)->ResearchProjection:
    check_text(raw,max_chars=max_chars,max_links=max_links)
    try:
        data=tomllib.loads(raw)
    except (ValueError,RecursionError) as exc:
        raise ResearchFormatError("invalid Python pylock TOML") from exc
    if not isinstance(data,dict) or str(data.get("lock-version","")) not in ("1","1.0"):
        raise ResearchFormatError("pylock version not supported")
    packages=data.get("packages")
    if not isinstance(packages,list) or not 1<=len(packages)<=256:
        raise ResearchFormatError("pylock package capacity exceeded")
    nodes=[]
    names={}
    for i,record in enumerate(packages,1):
        if not isinstance(record,dict):
            raise ResearchFormatError("invalid pylock package")
        name=label(record.get("name"))
        version=label(record.get("version",""),maxlen=128,empty=True)
        sid=f"pylock_{i}"
        nodes.append(SBOMComponent(sid,name,version,ecosystem="pypi"))
        names.setdefault(name,[]).append(sid)
    edges=[]
    for i,record in enumerate(packages,1):
        deps=record.get("dependencies",[])
        if not isinstance(deps,list) or len(deps)>128:
            raise ResearchFormatError("pylock dependency capacity exceeded")
        for dep in deps:
            if not isinstance(dep,dict) or not isinstance(dep.get("name"),str):
                raise ResearchFormatError("invalid pylock dependency")
            key=dep["name"]
            if len(key)>256:
                raise ResearchFormatError("pylock dependency name too long")
            candidates=names.get(key,[])
            if len(candidates)==1 and candidates[0]!=f"pylock_{i}":
                edges.append(SBOMEdge(f"pylock_{i}",candidates[0]))
        if len(edges)>2048:
            raise ResearchFormatError("pylock graph edge capacity exceeded")
    return project_sbom(make_sbom_graph(nodes,edges),
                        kind="Python pylock",max_chars=max_chars)
