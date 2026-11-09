"""Finite npm package-lock v2/v3 dependency graph, no installers or source fetch."""
from __future__ import annotations

import hashlib
import re

from .sbom_parsing import load, label, license_id
from .sbom_graph import SBOMComponent, SBOMEdge, make_sbom_graph, project_sbom
from .research_projection import ResearchFormatError, ResearchProjection

NPM_LOCK_TYPES=frozenset({"application/vnd.npm.package-lock+json"})
_PATH=re.compile(r"^[A-Za-z0-9@._/+-]{0,512}$")
_NAME=re.compile(r"^@?[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?$")
_MAX_PACKAGES=256

def _id(path:str)->str:
    return "npm_root" if not path else "npm_"+hashlib.sha256(path.encode()).hexdigest()[:24]

def _resolve(path:str,name:str,known:set[str])->str|None:
    if not _NAME.fullmatch(name):
        return None
    current=path
    for _ in range(32):
        candidate=current+"/node_modules/"+name if current else "node_modules/"+name
        if candidate in known:
            return candidate
        if not current:
            break
        current=current.rsplit("/node_modules/",1)[0] if "/node_modules/" in current else ""
        if current.startswith("node_modules/"):
            current=""
    return None

def extract_npm_lock(
    raw:str,*,max_chars:int=524288,max_links:int=0,
)->ResearchProjection:
    data=load(raw,max_chars=max_chars)
    if data.get("lockfileVersion") not in (2,3):
        raise ResearchFormatError("npm lockfile version unsupported")
    packages=data.get("packages")
    if not isinstance(packages,dict) or not 1<=len(packages)<=_MAX_PACKAGES:
        raise ResearchFormatError("npm package capacity exceeded")
    nodes=[]
    for path,record in sorted(packages.items()):
        if (not isinstance(path,str) or not _PATH.fullmatch(path)
                or ".." in path.split("/") or "\\" in path
                or not isinstance(record,dict)):
            raise ResearchFormatError("invalid npm package path or object")
        name=path.rsplit("/node_modules/",1)[-1].removeprefix("node_modules/")
        name=label(record.get("name",name or "Root project"))
        version=label(record.get("version",""),maxlen=128,empty=True)
        nodes.append(SBOMComponent(
            identity=_id(path),name=name,version=version,
            declared_license=license_id(record.get("license")),
            ecosystem="npm",hash_present=bool(record.get("integrity")),
        ))
    edges=[]
    known=set(packages)
    for path,record in sorted(packages.items()):
        deps=record.get("dependencies",{})
        if not isinstance(deps,dict) or len(deps)>128:
            raise ResearchFormatError("npm dependency fanout exceeded")
        for name in sorted(deps):
            if not isinstance(name,str) or not _NAME.fullmatch(name):
                raise ResearchFormatError("invalid npm dependency name")
            target=_resolve(path,name,known)
            if target and target!=path:
                edges.append(SBOMEdge(_id(path),_id(target)))
            if len(edges)>2048:
                raise ResearchFormatError("npm dependency graph capacity exceeded")
    return project_sbom(make_sbom_graph(nodes,edges),
                        kind="npm package-lock",max_chars=max_chars)
