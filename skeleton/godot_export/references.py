"""res:// reference resolution across scenes, resources, scripts and settings (GFD-05)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import tscn
from .project import GodotProject, path_to_res

_GD_RES = re.compile(r"""\b(?:preload|load|ResourceLoader\.load)\(\s*["'](res://[^"']+)["']""")
_ANY_RES = re.compile(r"""["'](res://[^"']+)["']""")


@dataclass(frozen=True)
class Dangling:
    source: str
    target: str
    kind: str


def scene_problems(project: GodotProject, scene_path: Path) -> list[Dangling]:
    src = path_to_res(project.root, scene_path)
    try:
        scene = tscn.load(scene_path)
    except tscn.SceneParseError as exc:
        return [Dangling(src, str(exc), "parse")]
    out: list[Dangling] = []
    ext_ids = set()
    for ext in scene.ext_resources:
        ext_ids.add(ext.id)
        if ext.path and not project.exists(ext.path):
            out.append(Dangling(src, ext.path, "ext_resource"))
    sub_ids = {str(b.attrs.get("id", "")) for b in scene.sub_resources}
    for kind, rid in sorted(scene.referenced_ids()):
        if kind == "ExtResource" and rid not in ext_ids:
            out.append(Dangling(src, rid, "ext_id"))
        if kind == "SubResource" and rid not in sub_ids:
            out.append(Dangling(src, rid, "sub_id"))
    return out


def script_problems(project: GodotProject, script_path: Path) -> list[Dangling]:
    src = path_to_res(project.root, script_path)
    text = script_path.read_text(encoding="utf-8", errors="replace")
    out = []
    for m in _GD_RES.finditer(text):
        if not project.exists(m.group(1)):
            out.append(Dangling(src, m.group(1), "load"))
    return out


def settings_problems(project: GodotProject) -> list[Dangling]:
    out = []
    main = project.main_scene
    if main and not project.exists(main):
        out.append(Dangling("project.godot", main, "main_scene"))
    for name, target in project.autoloads.items():
        if not project.exists(target):
            out.append(Dangling("project.godot", target, f"autoload:{name}"))
    icon = project.setting("application", "config/icon")
    if isinstance(icon, str) and icon and not project.exists(icon):
        out.append(Dangling("project.godot", icon, "icon"))
    return out


def all_problems(project: GodotProject) -> list[Dangling]:
    out = settings_problems(project)
    for s in project.scenes():
        if s.suffix == ".tscn":
            out.extend(scene_problems(project, s))
    for r in project.resources():
        if r.suffix == ".tres":
            out.extend(scene_problems(project, r))
    for g in project.scripts():
        out.extend(script_problems(project, g))
    return out
