"""Read-only OBJ geometry stats without material, texture or filesystem IO."""
from __future__ import annotations

import math
import re

from .research_projection import ResearchFormatError, ResearchProjection, check_text, project_lines

OBJ_MEDIA_TYPES = frozenset({"model/obj", "text/x-obj"})
_LABEL = re.compile(r"^[A-Za-z0-9_. -]{1,128}$")


def extract_obj(
    raw: str, *, max_chars: int = 524288, max_links: int = 0,
) -> ResearchProjection:
    check_text(raw, max_chars=max_chars, max_links=max_links)
    rows = raw.lstrip("\ufeff").splitlines()
    if not rows or len(rows) > 65536:
        raise ResearchFormatError("OBJ line count invalid")
    vertices = faces = normals = textures = 0
    groups = []
    bounds = [math.inf, math.inf, math.inf, -math.inf, -math.inf, -math.inf]
    for rawline in rows:
        if len(rawline) > 8192:
            raise ResearchFormatError("unbounded OBJ record")
        line = rawline.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        tag = fields[0]
        if tag == "v":
            if len(fields) not in (4, 5):
                raise ResearchFormatError("invalid OBJ vertex coordinate count")
            try:
                xyz = [float(x) for x in fields[1:4]]
            except ValueError as exc:
                raise ResearchFormatError("invalid OBJ coordinates") from exc
            if any(not math.isfinite(v) or abs(v) > 1_000_000 for v in xyz):
                raise ResearchFormatError("unbounded OBJ spatial extent")
            vertices += 1
            if vertices > 100000:
                raise ResearchFormatError("OBJ vertex count exceeded")
            for k,v in enumerate(xyz):
                bounds[k] = min(bounds[k], v)
                bounds[k+3] = max(bounds[k+3], v)
        elif tag in ("vt", "vn"):
            if len(fields) > 5:
                raise ResearchFormatError("invalid OBJ vector tuple")
            if tag == "vt":
                textures += 1
            else:
                normals += 1
        elif tag == "f":
            if not 3 <= len(fields)-1 <= 64:
                raise ResearchFormatError("invalid OBJ polygon arity")
            if not vertices:
                raise ResearchFormatError("OBJ face has no available vertices")
            for token in fields[1:]:
                number = token.split("/", 1)[0]
                if not re.fullmatch(r"-?[0-9]{1,8}", number):
                    raise ResearchFormatError("invalid OBJ face index")
                value = int(number)
                if value == 0 or abs(value) > vertices:
                    raise ResearchFormatError("OBJ face refers outside known vertices")
            faces += 1
            if faces > 100000:
                raise ResearchFormatError("OBJ face count exceeded")
        elif tag in ("g", "o"):
            label = " ".join(fields[1:])
            if label and _LABEL.fullmatch(label):
                if len(groups) < 64 and label not in groups:
                    groups.append(label)
        elif tag in ("mtllib", "usemtl"):
            # Material files and textures may not be dereferenced.
            continue
        else:
            # Unknown source directives are inert, never interpreted as IO.
            continue
    if not vertices:
        raise ResearchFormatError("OBJ source contains no vertices")
    lines = [
        "3D asset: Wavefront OBJ geometry metadata",
        f"Vertices: {vertices}; faces: {faces}; normals: {normals}; UV records: {textures}",
        "Coordinate bounds approx: " + ", ".join(f"{v:.2f}" for v in bounds),
        f"Named objects and groups: {', '.join(groups) if groups else '[none]'}",
        "Materials, references and texture files: not loaded",
    ]
    return project_lines(lines, title="OBJ geometry source", max_chars=max_chars)
