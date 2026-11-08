"""SPDX 2.2/2.3 JSON dependency inventory without asserting license rights."""
from __future__ import annotations

from .research_projection import ResearchFormatError, ResearchProjection
from .sbom_graph import SBOMComponent, SBOMEdge, make_sbom_graph, project_sbom
from .sbom_parsing import (
    load, identity, label, license_id, ecosystem_from_purl, count_rows,
)

SPDX_MEDIA_TYPES=frozenset({"application/spdx+json"})
_ALLOWED_REL=frozenset(("DEPENDS_ON","DEPENDENCY_OF"))


def _ecosystem(refs)->str:
    if not isinstance(refs,list) or len(refs)>32:
        raise ResearchFormatError("SPDX externalRef capacity exceeded")
    for ref in refs:
        if not isinstance(ref,dict):
            raise ResearchFormatError("invalid SPDX externalRef")
        if ref.get("referenceType") in ("purl","package-url"):
            return ecosystem_from_purl(ref.get("referenceLocator",""))
    return "unspecified"


def extract_spdx(
    raw:str,*,max_chars:int=524288,max_links:int=0,
)->ResearchProjection:
    doc=load(raw,max_chars=max_chars)
    version=doc.get("spdxVersion")
    if version not in ("SPDX-2.2","SPDX-2.3"):
        raise ResearchFormatError("unsupported SPDX JSON version")
    packages=count_rows(doc.get("packages",[]),"SPDX packages",256)
    if not packages:
        raise ResearchFormatError("empty SPDX package inventory")
    nodes=[]
    for row in packages:
        if not isinstance(row,dict):
            raise ResearchFormatError("malformed SPDX package")
        sid=identity(row.get("SPDXID"))
        name=label(row.get("name"))
        version=label(row.get("versionInfo",""),maxlen=128,empty=True)
        checksums=row.get("checksums",[])
        if not isinstance(checksums,list) or len(checksums)>16:
            raise ResearchFormatError("SPDX checksum count exceeded")
        nodes.append(SBOMComponent(
            identity=sid,name=name,version=version,
            declared_license=license_id(row.get("licenseDeclared")),
            ecosystem=_ecosystem(row.get("externalRefs",[])),
            hash_present=bool(checksums),
        ))
    relationships=count_rows(doc.get("relationships",[]),"SPDX relationships",1024)
    edges=[]
    for rel in relationships:
        if not isinstance(rel,dict):
            raise ResearchFormatError("invalid SPDX relationship")
        kind=rel.get("relationshipType")
        if kind not in _ALLOWED_REL:
            continue
        a=identity(rel.get("spdxElementId"))
        b=identity(rel.get("relatedSpdxElement"))
        if kind=="DEPENDENCY_OF":
            a,b=b,a
        edges.append(SBOMEdge(a,b))
        if len(edges)>2048:
            raise ResearchFormatError("SPDX dependency capacity exceeded")
    graph=make_sbom_graph(nodes,edges)
    return project_sbom(graph,kind="SPDX JSON",max_chars=max_chars)
