"""ASCII USD prim inventory without asset references, composition or rendering."""
from __future__ import annotations
from collections import Counter
import re
from .research_projection import ResearchFormatError, ResearchProjection, check_text, project_lines
from .usda_hierarchy import inspect_usda_hierarchy
from .scene_topology import summarize_scene_topology

USDA_TYPES=frozenset({"model/vnd.usda","application/x-usda"})
_PRIM=re.compile(
    r'^\s*(?:def|over|class)\s+([A-Za-z_][A-Za-z0-9_]{0,100})'
    r'\s+"([A-Za-z0-9_ .-]{1,128})"(?:\s*\(|\s*\{|\s*$)'
)


def extract_usda(
    raw:str,*,max_chars:int=524288,max_links:int=0,
)->ResearchProjection:
    check_text(raw,max_chars=max_chars,max_links=max_links)
    lines=raw.lstrip("\ufeff").splitlines()
    if (not lines or len(lines)>32768 or lines[0].strip()!="#usda 1.0"):
        raise ResearchFormatError("USD ASCII v1.0 source signature missing")
    types=Counter()
    names=[]
    for row in lines[1:]:
        if len(row)>8192:
            raise ResearchFormatError("USD prim source line exceeds bound")
        match=_PRIM.match(row)
        if match:
            types[match.group(1)]+=1
            if len(names)<64:
                names.append(match.group(2))
            if sum(types.values())>4096:
                raise ResearchFormatError("USD scene prim capacity exceeded")
    if not types:
        raise ResearchFormatError("USD scene contains no declared prims")
    output=[
        "Game/3D source: ASCII Universal Scene Description (unreviewed)",
        f"Declared prims: {sum(types.values())}",
        "Prim type counts: "+", ".join(f"{key}={val}" for key,val in sorted(types.items())),
        "Sample prim names: "+", ".join(names[:16]),
        "USD composition, references, payloads and asset resolution: disabled",
    ]
    try:
        topology=inspect_usda_hierarchy(raw)
    except ResearchFormatError:
        # A foreign USD composition syntax is not proof of an executable
        # source. Keep basic unreviewed class counts but omit topology claims.
        output.append("USD scope topology: unqualified foreign syntax")
    else:
        output.extend(summarize_scene_topology(topology))
    return project_lines(output,title="USD scene inventory",max_chars=max_chars)
