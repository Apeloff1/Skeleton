"""Finite Cargo.lock 3/4 graph, no builds, compilation, registry or network IO."""
from __future__ import annotations

import re
import tomllib
from .sbom_graph import SBOMComponent, SBOMEdge, make_sbom_graph, project_sbom
from .sbom_parsing import label
from .research_projection import ResearchFormatError, ResearchProjection, check_text

CARGO_LOCK_TYPES=frozenset({"application/vnd.cargo.lock+toml","text/x-cargo-lock"})
_NAME=re.compile(r"^[A-Za-z0-9_-]{1,128}$")

def extract_cargo_lock(
    raw:str,*,max_chars:int=524288,max_links:int=0,
)->ResearchProjection:
    check_text(raw,max_chars=max_chars,max_links=max_links)
    try:
        data=tomllib.loads(raw)
    except (ValueError,RecursionError) as exc:
        raise ResearchFormatError("malformed Cargo lock TOML") from exc
    if not isinstance(data,dict) or data.get("version") not in (3,4):
        raise ResearchFormatError("unsupported Cargo.lock version")
    packages=data.get("package")
    if not isinstance(packages,list) or not 1<=len(packages)<=256:
        raise ResearchFormatError("Cargo lock component capacity exceeded")
    nodes=[]
    by_name={}
    for i,record in enumerate(packages,1):
        if not isinstance(record,dict):
            raise ResearchFormatError("invalid Cargo lock package")
        name=record.get("name")
        if not isinstance(name,str) or not _NAME.fullmatch(name):
            raise ResearchFormatError("invalid Cargo crate name")
        version=label(record.get("version",""),maxlen=128,empty=True)
        checksum=record.get("checksum")
        nodes.append(SBOMComponent(
            identity=f"cargo_{i}",name=name,version=version,
            ecosystem="cargo",hash_present=bool(checksum),
        ))
        by_name.setdefault(name,[]).append((f"cargo_{i}",version))
    edges=[]
    for i,record in enumerate(packages,1):
        deps=record.get("dependencies",[])
        if not isinstance(deps,list) or len(deps)>128:
            raise ResearchFormatError("Cargo dependency fanout exceeded")
        for item in deps:
            if not isinstance(item,str) or len(item)>1024:
                raise ResearchFormatError("Cargo dependency entry invalid")
            tokens=item.split()
            if not tokens:
                raise ResearchFormatError("Cargo dependency entry empty")
            options=by_name.get(tokens[0],[])
            if len(tokens)>=2:
                options=[row for row in options if row[1]==tokens[1]]
            if len(options)==1 and options[0][0]!=f"cargo_{i}":
                edges.append(SBOMEdge(f"cargo_{i}",options[0][0]))
            if len(edges)>2048:
                raise ResearchFormatError("Cargo graph limit exceeded")
    return project_sbom(make_sbom_graph(nodes,edges),
                        kind="Cargo.lock",max_chars=max_chars)
