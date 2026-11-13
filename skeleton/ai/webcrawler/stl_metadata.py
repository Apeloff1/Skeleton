"""Finite binary STL triangle bounds, never importing or rendering mesh data."""
from __future__ import annotations
import math
import struct
from .research_projection import ResearchFormatError, ResearchProjection, project_lines

STL_TYPES=frozenset({"model/stl","application/sla"})


def extract_binary_stl(body: bytes, *, max_chars: int=524288)->ResearchProjection:
    if (type(body) is not bytes or len(body)>2_097_152 or len(body)<84
            or type(max_chars) is not int or max_chars<1):
        raise ResearchFormatError("STL envelope invalid")
    triangles=struct.unpack("<I",body[80:84])[0]
    if not 1<=triangles<=40000 or len(body)!=84+50*triangles:
        raise ResearchFormatError("binary STL triangle framing mismatch")
    low=[math.inf]*3
    high=[-math.inf]*3
    for i in range(triangles):
        # STL facet has 3 normal floats, 9 vertex floats, 2 attribute bytes.
        facet=body[84+50*i:84+50*(i+1)]
        coords=struct.unpack("<12f",facet[:48])
        for j in range(3):
            for v in (coords[j+3],coords[j+6],coords[j+9]):
                if not math.isfinite(v) or abs(v)>1_000_000:
                    raise ResearchFormatError("nonfinite or excessive STL coordinate")
                low[j]=min(low[j],v)
                high[j]=max(high[j],v)
    return project_lines([
        "3D mesh: binary STL triangle metadata",
        f"Triangles: {triangles}; vertices advertised: {triangles*3}",
        "Spatial bounds approx: "+", ".join(f"{x:.2f}" for x in low+high),
        "Mesh normals/material attributes: not executed or rendered",
    ],title="STL mesh metadata",max_chars=max_chars)
