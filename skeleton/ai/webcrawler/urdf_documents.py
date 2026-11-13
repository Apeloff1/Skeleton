"""URDF link/joint tree source analysis, no ROS/xacro/mesh/plugin execution."""
from __future__ import annotations

from collections import Counter

from .robot_xml_guard import (
    source_tree,exact_name,finite_number,topology_for_links,
)
from .scene_topology import summarize_scene_topology
from .research_projection import ResearchFormatError,ResearchProjection,project_lines

URDF_TYPES=frozenset({"model/urdf+xml","application/x-urdf+xml"})
_JOINT_TYPES=frozenset({
    "revolute","continuous","prismatic","fixed","floating","planar",
})


def extract_urdf(
    raw:str,*,max_chars:int=524288,max_links:int=0,
)->ResearchProjection:
    robot=source_tree(raw,max_chars=max_chars,root_tag="robot")
    if robot.get("name") is not None:
        exact_name(robot.get("name"))
    links=[]
    joint_edges=[]
    joint_types=Counter()
    joint_names=set()
    visuals=colliders=meshes=mimics=0
    for row in robot:
        if row.tag=="link":
            name=exact_name(row.get("name"))
            links.append(name)
            if len(links)>512:
                raise ResearchFormatError("URDF link count exceeded")
            for kind in ("visual","collision"):
                entries=row.findall(kind)
                if len(entries)>64:
                    raise ResearchFormatError("URDF visual/collision capacity exceeded")
                if kind=="visual":
                    visuals+=len(entries)
                else:
                    colliders+=len(entries)
                for block in entries:
                    geometry=block.find("geometry")
                    if geometry is not None:
                        meshes+=len(geometry.findall("mesh"))
            if visuals+colliders+meshes>8192:
                raise ResearchFormatError("URDF geometry declaration capacity exceeded")
            for mass in row.findall("./inertial/mass"):
                finite_number(mass.get("value"),minval=0,maxval=1e9)
        elif row.tag=="joint":
            name=exact_name(row.get("name"))
            kind=row.get("type")
            if name in joint_names or kind not in _JOINT_TYPES:
                raise ResearchFormatError("URDF duplicate joint or unsupported type")
            joint_names.add(name)
            parent=row.find("parent")
            child=row.find("child")
            if parent is None or child is None:
                raise ResearchFormatError("URDF joint parent/child absent")
            p,c=exact_name(parent.get("link")),exact_name(child.get("link"))
            joint_edges.append((p,c))
            joint_types[kind]+=1
            if len(joint_edges)>1024:
                raise ResearchFormatError("URDF joint count exceeded")
            for limit in row.findall("limit"):
                for attr in ("lower","upper","velocity","effort"):
                    if attr in limit.attrib:
                        finite_number(limit.attrib[attr])
            mimics+=len(row.findall("mimic"))
        # Xacro macros, plugins and linked meshes cannot be loaded.
    topology=topology_for_links("URDF",links,joint_edges)
    lines=[
        "Robotics source: inert URDF articulated model",
        f"Links: {len(links)}; joints: {len(joint_edges)}",
        "Joint type counts: "+", ".join(f"{key}={val}" for key,val in sorted(joint_types.items())),
        f"Visual objects: {visuals}; collision objects: {colliders}; mesh refs: {meshes}",
        f"Mimic annotations declared (not evaluated): {mimics}",
        *summarize_scene_topology(topology),
        "ROS, xacro, dynamic joints, meshes, plugins and world simulation: disabled",
    ]
    return project_lines(lines,title="URDF articulation inventory",max_chars=max_chars)
