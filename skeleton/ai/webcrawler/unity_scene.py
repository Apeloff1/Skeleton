"""Unity YAML asset class inventory, with no YAML object construction."""
from __future__ import annotations
from collections import Counter
import re
from .research_projection import ResearchFormatError, ResearchProjection, check_text, project_lines
from .unity_hierarchy import inspect_unity_hierarchy
from .scene_topology import summarize_scene_topology

UNITY_TYPES=frozenset({"application/x-unity-scene","text/x-unity-scene"})
_OBJECT=re.compile(r"^--- !u!(\d{1,5}) &(-?\d{1,20})$")
_SAFE_NAME=re.compile(r"^[A-Za-z0-9_ .-]{1,128}$")
_CLASS_NAMES={
    1:"GameObject",4:"Transform",20:"Camera",21:"Material",
    23:"MeshRenderer",33:"MeshFilter",54:"Rigidbody",
    95:"Animator",114:"MonoBehaviour",212:"SpriteRenderer",
    224:"RectTransform",
}


def extract_unity_scene(
    raw:str,*,max_chars:int=524288,max_links:int=0,
)->ResearchProjection:
    check_text(raw,max_chars=max_chars,max_links=max_links)
    rows=raw.lstrip("\ufeff").splitlines()
    if (not rows or len(rows)>32768 or rows[0].strip()!="%YAML 1.1"):
        raise ResearchFormatError("Unity YAML source signature missing")
    objects=Counter()
    ids=set()
    names=[]
    active=False
    for row in rows[1:]:
        if len(row)>8192:
            raise ResearchFormatError("Unity YAML source line too long")
        match=_OBJECT.fullmatch(row.strip())
        if match:
            kind=int(match.group(1))
            identity=match.group(2)
            if identity in ids:
                raise ResearchFormatError("Unity asset file identity collision")
            ids.add(identity)
            objects[kind]+=1
            active=True
            if sum(objects.values())>8192:
                raise ResearchFormatError("Unity object count exceeded")
            continue
        if row.startswith("---") and not match:
            raise ResearchFormatError("unsupported Unity document header")
        if active and row.lstrip().startswith("m_Name:"):
            name=row.split(":",1)[1].strip().strip('"')
            if _SAFE_NAME.fullmatch(name) and len(names)<64:
                names.append(name)
    if not objects:
        raise ResearchFormatError("Unity scene has no object inventory")
    output=[
        "Game-engine source: Unity YAML scene (no YAML evaluation)",
        f"Serialized object records: {sum(objects.values())}",
        "Declared object classes: "+", ".join(
            f"{_CLASS_NAMES.get(key,'class_'+str(key))}={num}"
            for key,num in sorted(objects.items())
        ),
        "Example object names: "+(", ".join(names[:16]) or "[none]"),
        "MonoBehaviour scripts, external assets and YAML tags: not loaded",
    ]
    topology=inspect_unity_hierarchy(raw)
    if topology is not None:
        output.extend(summarize_scene_topology(topology.topology))
        output.append(f"Unresolved local Transform parent anchors: {topology.unresolved_parent_count}")
    return project_lines(output,title="Unity scene inventory",max_chars=max_chars)
