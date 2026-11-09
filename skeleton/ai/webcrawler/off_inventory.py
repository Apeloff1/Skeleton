"""Finite OFF mesh vertex/face inventory without object execution or rendering."""
from __future__ import annotations
import math
from .research_projection import ResearchFormatError, ResearchProjection, check_text, project_lines

OFF_TYPES=frozenset({"model/off","text/x-off"})


def _records(raw:str)->list[str]:
    lines=[line.strip() for line in raw.lstrip("\ufeff").splitlines()]
    return [line for line in lines if line and not line.startswith("#")]


def extract_off(raw:str,*,max_chars:int=524288,max_links:int=0)->ResearchProjection:
    check_text(raw,max_chars=max_chars,max_links=max_links)
    lines=_records(raw)
    if len(lines)<3 or len(lines)>131072 or lines[0]!="OFF":
        raise ResearchFormatError("OFF text geometry signature missing")
    counts=lines[1].split()
    if len(counts)!=3 or not all(x.isdigit() for x in counts):
        raise ResearchFormatError("OFF vertex/face/edge counts malformed")
    vertices,faces,edges=map(int,counts)
    if not 1<=vertices<=100000 or faces>100000 or edges>200000:
        raise ResearchFormatError("OFF geometry capacity exceeded")
    if len(lines)!=2+vertices+faces:
        raise ResearchFormatError("OFF geometry rows do not match declared counts")
    low=[math.inf]*3
    high=[-math.inf]*3
    for row in lines[2:2+vertices]:
        cells=row.split()
        if len(cells)<3 or len(cells)>7:
            raise ResearchFormatError("OFF coordinate record invalid")
        try:xyz=[float(x) for x in cells[:3]]
        except ValueError as exc:
            raise ResearchFormatError("invalid OFF floating coordinates") from exc
        if any(not math.isfinite(x) or abs(x)>1e6 for x in xyz):
            raise ResearchFormatError("OFF geometry outside finite scene extent")
        for i,val in enumerate(xyz):
            low[i]=min(low[i],val)
            high[i]=max(high[i],val)
    for row in lines[2+vertices:]:
        cells=row.split()
        if not cells or not cells[0].isdigit():
            raise ResearchFormatError("OFF polygon count absent")
        size=int(cells[0])
        if size<3 or size>64 or len(cells)<size+1:
            raise ResearchFormatError("OFF polygon arity invalid")
        for cell in cells[1:size+1]:
            if not cell.isdigit() or int(cell)>=vertices:
                raise ResearchFormatError("OFF out-of-range vertex index")
    return project_lines([
        "3D asset: OFF mesh inventory",
        f"Vertices: {vertices}; faces: {faces}; declared_edges: {edges}",
        "Spatial bounds approximate: "+", ".join(f"{x:.2f}" for x in low+high),
        "Mesh geometry: not rendered, imported or executed",
    ],title="OFF mesh inventory",max_chars=max_chars)
