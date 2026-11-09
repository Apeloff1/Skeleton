"""Bounded SDF robot model source topology; no Gazebo plugins or mesh IO."""
from __future__ import annotations

from collections import Counter

from .robot_xml_guard import (
    source_tree,exact_name,finite_number,topology_for_links,
)
from .scene_topology import summarize_scene_topology
from .research_projection import ResearchFormatError,ResearchProjection,project_lines

SDF_TYPES=frozenset({"model/sdf+xml","application/x-sdf+xml"})
_JOINTS=frozenset({
    "revolute","revolute2","prismatic","ball","universal",
    "screw","fixed","gearbox",
})


def extract_sdf(
    raw:str,*,max_chars:int=524288,max_links:int=0,
)->ResearchProjection:
    root=source_tree(raw,max_chars=max_chars,root_tag="sdf")
    version=root.get("version")
    if version not in ("1.6","1.7","1.8","1.9","1.10","1.11"):
        raise ResearchFormatError("SDF source version unsupported")
    models=root.findall("model")
    if len(models)!=1:
        raise ResearchFormatError("SDF crawler supports one explicit model")
    model=models[0]
    exact_name(model.get("name"))
    links=[]
    geometry=Counter()
    meshes=0
    for row in model.findall("link"):
        links.append(exact_name(row.get("name")))
        if len(links)>512:
            raise ResearchFormatError("SDF link count exceeded")
        for kind in ("visual","collision","sensor"):
            entries=row.findall(kind)
            geometry[kind]+=len(entries)
            if geometry[kind]>2048:
                raise ResearchFormatError("SDF visual/collider/sensor capacity exceeded")
            for block in entries:
                meshes+=len(block.findall("./geometry/mesh"))
        for mass in row.findall("./inertial/mass"):
            if mass.text is not None:
                finite_number(mass.text.strip(),minval=0,maxval=1e9)
    edges=[]
    types=Counter()
    seen=set()
    for row in model.findall("joint"):
        name=exact_name(row.get("name"))
        kind=row.get("type")
        if name in seen or kind not in _JOINTS:
            raise ResearchFormatError("SDF joint identity or declared type invalid")
        seen.add(name)
        parent=row.findtext("parent")
        child=row.findtext("child")
        if not parent or not child:
            raise ResearchFormatError("SDF joint endpoints missing")
        edges.append((exact_name(parent.strip()),exact_name(child.strip())))
        types[kind]+=1
        if len(edges)>1024:
            raise ResearchFormatError("SDF joint capacity exceeded")
    includes=len(model.findall("include"))+len(root.findall("include"))
    if includes>64 or meshes>4096:
        raise ResearchFormatError("SDF include or mesh declaration capacity exceeded")
    topology=topology_for_links("SDF",links,edges)
    lines=[
        "Robotics/physics source: inert SDF model",
        f"SDF version: {version}; articulated links: {len(links)}",
        f"Joint declarations: {len(edges)}; "
        f"visuals: {geometry['visual']}; collisions: {geometry['collision']}",
        f"Sensors declared: {geometry['sensor']}; meshes: {meshes}",
        f"External includes declared but not loaded: {includes}",
        "Joint categories: "+", ".join(f"{key}={n}" for key,n in sorted(types.items())),
        *summarize_scene_topology(topology),
        "Gazebo physics, plugins, sensors and external resource loading: disabled",
    ]
    return project_lines(lines,title="SDF model source",max_chars=max_chars)
