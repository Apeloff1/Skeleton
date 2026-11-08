"""Read-only MuJoCo MJCF source body hierarchy, no physics engine execution."""
from __future__ import annotations

from collections import Counter
import hashlib

from .robot_xml_guard import source_tree,exact_name,finite_number
from .scene_topology import SceneNode,SceneEdge,analyze_scene_topology,summarize_scene_topology
from .research_projection import ResearchFormatError,ResearchProjection,project_lines

MJCF_TYPES=frozenset({"application/x-mjcf+xml","model/mjcf+xml"})


def _id(path:str)->str:
    return "body_"+hashlib.sha256(path.encode()).hexdigest()[:24]


def extract_mjcf(
    raw:str,*,max_chars:int=524288,max_links:int=0,
)->ResearchProjection:
    root=source_tree(raw,max_chars=max_chars,root_tag="mujoco")
    if root.get("model") is not None:
        exact_name(root.get("model"))
    world=root.find("worldbody")
    if world is None:
        raise ResearchFormatError("MJCF worldbody source element missing")
    nodes=[]
    edges=[]
    known=set()
    objects=Counter()
    stack=[(body,"",0,i) for i,body in enumerate(reversed(world.findall("body")))]
    visited=0
    while stack:
        body,parent,depth,index=stack.pop()
        visited+=1
        if visited>512 or depth>32:
            raise ResearchFormatError("MJCF body count or hierarchy depth exceeded")
        name=body.get("name") or f"unnamed_{index}"
        name=exact_name(name)
        path=parent+"/"+name if parent else name
        if path in known:
            raise ResearchFormatError("duplicate MJCF body source identity")
        known.add(path)
        nodes.append(SceneNode(_id(path),"Body","MJCF body"))
        if parent:
            edges.append(SceneEdge(_id(parent),_id(path)))
        for kind in ("joint","freejoint","geom","site","camera","light"):
            rows=body.findall(kind)
            objects[kind]+=len(rows)
            if objects[kind]>4096:
                raise ResearchFormatError("MJCF source object declarations exceed cap")
            for row in rows:
                if kind=="joint" and "range" in row.attrib:
                    parts=row.attrib["range"].split()
                    if len(parts)!=2:
                        raise ResearchFormatError("MJCF joint range arity invalid")
                    for value in parts:
                        finite_number(value)
        children=body.findall("body")
        if len(children)>128:
            raise ResearchFormatError("MJCF child body fanout exceeded")
        stack.extend((child,path,depth+1,i)
                     for i,child in enumerate(reversed(children)))
    if not nodes:
        raise ResearchFormatError("MJCF source has no articulated bodies")
    includes=len(root.findall("include"))+len(world.findall("include"))
    assets=root.find("asset")
    mesh_count=(len(assets.findall("mesh")) if assets is not None else 0)
    if includes>64 or mesh_count>512:
        raise ResearchFormatError("MJCF import/mesh declarations exceed bound")
    topology=analyze_scene_topology("MJCF",nodes,edges,max_nodes=512,max_edges=1024)
    output=[
        "Physics/robotics source: inert MJCF body graph",
        f"Declared bodies: {len(nodes)}; joints: {objects['joint']}; "
        f"freejoints: {objects['freejoint']}",
        f"Geom objects: {objects['geom']}; sites: {objects['site']}; "
        f"cameras: {objects['camera']}; lights: {objects['light']}",
        f"Mesh asset declarations: {mesh_count}; includes: {includes} (not loaded)",
        *summarize_scene_topology(topology),
        "MuJoCo physics, plugins, shaders, meshes and actuator commands: disabled",
    ]
    return project_lines(output,title="MJCF articulated source",max_chars=max_chars)
