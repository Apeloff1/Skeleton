"""Godot text scene structural inventory without resource load or script run."""
from __future__ import annotations
from collections import Counter
import re
from .research_projection import ResearchFormatError, ResearchProjection, check_text, project_lines
from .godot_hierarchy import inspect_godot_hierarchy
from .scene_topology import summarize_scene_topology

GODOT_TYPES=frozenset({"application/x-godot-scene","text/x-godot-scene"})
_HEADER=re.compile(r"^\[gd_scene\s+[^\]\r\n]{0,512}\]$")
_NODE=re.compile(r'^\[node\s+name="([A-Za-z0-9_ .-]{1,128})"\s+type="([A-Za-z0-9_]{1,96})"([^\]\r\n]{0,512})\]$')
_RESOURCE=re.compile(r"^\[(ext_resource|sub_resource)\s+([^\]\r\n]{1,512})\]$")
_TYPE=re.compile(r'\btype="([A-Za-z0-9_]{1,96})"')
_ALLOWED_SECTION=re.compile(r"^\[[a-z_][a-z0-9_]*[^\]\r\n]{0,512}\]$")


def extract_godot_scene(
    raw:str,*,max_chars:int=524288,max_links:int=0,
)->ResearchProjection:
    check_text(raw,max_chars=max_chars,max_links=max_links)
    rows=raw.lstrip("\ufeff").splitlines()
    if not rows or len(rows)>8192 or not _HEADER.fullmatch(rows[0].strip()):
        raise ResearchFormatError("Godot scene document header missing")
    if "format=3" not in rows[0]:
        raise ResearchFormatError("only Godot scene format 3 supported")
    nodes=Counter()
    resources=Counter()
    names=[]
    for row in rows[1:]:
        if len(row)>8192:
            raise ResearchFormatError("Godot scene property line too large")
        line=row.strip()
        if not line or line.startswith(";"):
            continue
        if not line.startswith("["):
            # Property values are not evaluated, script bodies are inert.
            continue
        match=_NODE.fullmatch(line)
        if match:
            nodes[match.group(2)]+=1
            if sum(nodes.values())>2048:
                raise ResearchFormatError("Godot node capacity exceeded")
            if len(names)<64:
                names.append(match.group(1))
            continue
        match=_RESOURCE.fullmatch(line)
        if match:
            typ=_TYPE.search(match.group(2))
            if typ is None:
                raise ResearchFormatError("Godot resource type missing")
            resources[typ.group(1)]+=1
            if sum(resources.values())>512:
                raise ResearchFormatError("Godot resource capacity exceeded")
            continue
        if not _ALLOWED_SECTION.fullmatch(line):
            raise ResearchFormatError("unrecognized Godot scene section")
    if not nodes:
        raise ResearchFormatError("Godot scene contains no nodes")
    output=[
        "Game-engine source: Godot scene (unreviewed, not executed)",
        f"Scene nodes: {sum(nodes.values())}; resource declarations: {sum(resources.values())}",
        "Node classes: "+", ".join(f"{key}={count}" for key,count in sorted(nodes.items())),
        "Resource classes: "+(", ".join(f"{key}={count}" for key,count in sorted(resources.items())) or "[none]"),
        "Example node labels: "+", ".join(names[:16]),
        "Scripts, resources, shaders, file paths and imports: not loaded",
        *summarize_scene_topology(inspect_godot_hierarchy(raw)),
    ]
    return project_lines(output,title="Godot scene inventory",max_chars=max_chars)
