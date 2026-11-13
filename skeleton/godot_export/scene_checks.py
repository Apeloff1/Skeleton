"""Static physics/scene fidelity checks (GFS-01..03; GF-P0-38/74/96 static halves).

These complement, not replace, the native runtime checks in
``scripts/run_game_frontier_gfd_native_checks.py``: they catch authoring
defects (zero mass, unpinned soft bodies, no current camera) before the engine
is launched.
"""
from __future__ import annotations


from . import tscn
from .project import GodotProject, path_to_res
from .report import CaseResult


def _num(v: object, default: float) -> float:
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def rigid_bodies(project: GodotProject, scene: tscn.Scene, res: str) -> list[CaseResult]:
    out = []
    for n in scene.nodes_of_type("RigidBody3D"):
        mass = _num(n.props.get("mass", 1.0), -1)
        out.append(CaseResult("GFS-01", mass > 0, {"node": n.path, "mass": mass}, res))
    return out


def soft_bodies(project: GodotProject, scene: tscn.Scene, res: str) -> list[CaseResult]:
    out = []
    for n in scene.nodes_of_type("SoftBody3D"):
        mass = _num(n.props.get("total_mass", 1.0), -1)
        pinned = n.props.get("pinned_points", [])
        count = len(pinned.args) if hasattr(pinned, "args") else len(pinned) if isinstance(pinned, list) else 0
        ok = mass > 0 and count > 0
        out.append(CaseResult("GFS-02", ok, {"node": n.path, "total_mass": mass, "pinned": count}, res))
    return out


def current_camera(scene: tscn.Scene, res: str) -> CaseResult | None:
    root = scene.root()
    if root is None or root.type not in ("Node3D", "Spatial") and not any(n.type == "Camera3D" for n in scene.nodes):
        return None
    cams = scene.nodes_of_type("Camera3D")
    current = [c.path for c in cams if c.props.get("current") is True]
    return CaseResult("GFS-03", len(current) == 1, {"cameras": [c.path for c in cams], "current": current}, res)


def run_all(project: GodotProject) -> list[CaseResult]:
    out: list[CaseResult] = []
    main = project.main_scene
    for path in project.scenes():
        if path.suffix != ".tscn":
            continue
        res = path_to_res(project.root, path)
        try:
            scene = tscn.load(path)
        except tscn.SceneParseError:
            continue  # reported by GFD-05
        out.extend(rigid_bodies(project, scene, res))
        out.extend(soft_bodies(project, scene, res))
        if res == main:
            cam = current_camera(scene, res)
            if cam:
                out.append(cam)
    return out
