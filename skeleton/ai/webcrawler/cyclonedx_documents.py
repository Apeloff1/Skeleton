"""CycloneDX JSON v1.4–1.6 SBOM component topology, no external lookups."""
from __future__ import annotations
from .research_projection import ResearchFormatError, ResearchProjection
from .sbom_graph import SBOMComponent, SBOMEdge, make_sbom_graph, project_sbom
from .sbom_parsing import load, identity, label, license_id, ecosystem_from_purl, count_rows

CYCLONEDX_MEDIA_TYPES=frozenset({"application/vnd.cyclonedx+json"})


def _license(component:dict)->str:
    licenses=component.get("licenses",[])
    if not isinstance(licenses,list) or len(licenses)>16:
        raise ResearchFormatError("CycloneDX license array exceeds bound")
    declared=[]
    for row in licenses:
        if not isinstance(row,dict):
            raise ResearchFormatError("invalid CycloneDX license evidence")
        item=row.get("license")
        if isinstance(item,dict):
            val=license_id(item.get("id"))
            if val!="NOASSERTION":
                declared.append(val)
        elif row.get("expression"):
            declared.append(license_id(row["expression"]))
    return declared[0] if len(set(declared))==1 and declared else "NOASSERTION"


def extract_cyclonedx(
    raw:str,*,max_chars:int=524288,max_links:int=0,
)->ResearchProjection:
    doc=load(raw,max_chars=max_chars)
    if (doc.get("bomFormat")!="CycloneDX"
            or doc.get("specVersion") not in ("1.4","1.5","1.6")):
        raise ResearchFormatError("unsupported CycloneDX JSON version")
    rows=count_rows(doc.get("components",[]),"CycloneDX component",256)
    if not rows:
        raise ResearchFormatError("empty CycloneDX software inventory")
    components=[]
    for index,item in enumerate(rows):
        if not isinstance(item,dict):
            raise ResearchFormatError("malformed CycloneDX component")
        node_id=identity(item.get("bom-ref",f"component_{index+1}"))
        name=label(item.get("name"))
        version=label(item.get("version",""),maxlen=128,empty=True)
        hashes=item.get("hashes",[])
        if not isinstance(hashes,list) or len(hashes)>16:
            raise ResearchFormatError("CycloneDX hash array capacity exceeded")
        # External hash values are not verified or projected.
        components.append(SBOMComponent(
            identity=node_id,name=name,version=version,
            declared_license=_license(item),
            ecosystem=ecosystem_from_purl(item.get("purl","")),
            hash_present=bool(hashes),
        ))
    raw_edges=count_rows(doc.get("dependencies",[]),"CycloneDX dependencies",512)
    edges=[]
    for row in raw_edges:
        if not isinstance(row,dict):
            raise ResearchFormatError("invalid CycloneDX dependency row")
        parent=identity(row.get("ref"))
        targets=count_rows(row.get("dependsOn",[]),"CycloneDX dependency fanout",64)
        edges.extend(SBOMEdge(parent,identity(target)) for target in targets)
        if len(edges)>2048:
            raise ResearchFormatError("CycloneDX graph edge count exceeded")
    graph=make_sbom_graph(components,edges)
    return project_sbom(graph,kind="CycloneDX JSON",max_chars=max_chars)
