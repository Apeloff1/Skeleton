"""Read-only bounded ASCII PLY vertex/face geometry inventory."""
from __future__ import annotations
import math
from .research_projection import ResearchFormatError, ResearchProjection, check_text, project_lines

PLY_TYPES=frozenset({"model/ply","application/x-ply"})


def extract_ply(raw:str,*,max_chars:int=524288,max_links:int=0)->ResearchProjection:
    check_text(raw,max_chars=max_chars,max_links=max_links)
    rows=raw.lstrip("\ufeff").splitlines()
    if not rows or len(rows)>131072 or rows[0].strip()!="ply":
        raise ResearchFormatError("PLY source is missing a finite header")
    if len(rows)<4 or rows[1].strip()!="format ascii 1.0":
        raise ResearchFormatError("only ASCII PLY v1.0 is admitted")
    vertex=face=0
    cursor=2
    section=None
    properties=[]
    while cursor<len(rows) and cursor<=1024:
        row=rows[cursor].strip()
        cursor+=1
        if row=="end_header":
            break
        if row.startswith("comment ") or row.startswith("obj_info "):
            continue
        parts=row.split()
        if len(parts)==3 and parts[0]=="element":
            name=parts[1]
            if name not in ("vertex","face") or not parts[2].isdigit():
                raise ResearchFormatError("PLY element kind/count unsupported")
            count=int(parts[2])
            if count>100000:
                raise ResearchFormatError("PLY element capacity exceeded")
            if name=="vertex":
                if vertex:raise ResearchFormatError("duplicate PLY vertex element")
                vertex=count
            else:
                if face:raise ResearchFormatError("duplicate PLY face element")
                face=count
            section=name
        elif parts[:1]==["property"]:
            if section=="vertex":
                if len(parts)!=3 or len(properties)>32:
                    raise ResearchFormatError("invalid PLY vertex property")
                properties.append((parts[1],parts[2]))
            elif section=="face":
                # Face declaration is inert, not followed as an external mesh.
                if len(parts)<3 or len(parts)>5:
                    raise ResearchFormatError("invalid PLY face property")
            else:
                raise ResearchFormatError("PLY property outside element")
        else:
            raise ResearchFormatError("unrecognized PLY header")
    else:
        raise ResearchFormatError("PLY header terminator missing")
    if not vertex or tuple(x[1] for x in properties[:3])!=("x","y","z"):
        raise ResearchFormatError("PLY XYZ vertex properties missing")
    if len(rows)-cursor<vertex+face:
        raise ResearchFormatError("PLY claimed vertices or faces truncated")
    low=[math.inf]*3
    high=[-math.inf]*3
    for i in range(vertex):
        columns=rows[cursor+i].split()
        if len(columns)!=len(properties):
            raise ResearchFormatError("PLY vertex width mismatch")
        try:xyz=[float(v) for v in columns[:3]]
        except ValueError as exc:
            raise ResearchFormatError("non-numeric PLY coordinate") from exc
        if any(not math.isfinite(v) or abs(v)>1e6 for v in xyz):
            raise ResearchFormatError("PLY coordinate extent invalid")
        for j,val in enumerate(xyz):
            low[j]=min(low[j],val)
            high[j]=max(high[j],val)
    cursor+=vertex
    for i in range(face):
        cells=rows[cursor+i].split()
        if not cells or not cells[0].isdigit():
            raise ResearchFormatError("PLY face index count absent")
        size=int(cells[0])
        if size<3 or size>64 or len(cells)!=size+1:
            raise ResearchFormatError("PLY face arity unsupported")
        for index in cells[1:]:
            if not index.isdigit() or int(index)>=vertex:
                raise ResearchFormatError("PLY face references absent vertex")
    if any(row.strip() for row in rows[cursor+face:]):
        raise ResearchFormatError("PLY trailing records outside header manifest")
    labels=[
        "3D mesh: finite ASCII PLY inventory",
        f"Vertices: {vertex}; polygon faces: {face}",
        "Coordinate bounds approximate: "+", ".join(f"{v:.2f}" for v in low+high),
        "PLY attachments, materials and external references: not loaded",
    ]
    return project_lines(labels,title="PLY mesh inventory",max_chars=max_chars)
