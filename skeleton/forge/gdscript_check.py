"""Static Godot project checker — the engine binary here is aarch64, this box is x86_64.

Until a matching editor can --check-only, we refuse to emit a tree whose
res:// graph does not close, whose autoloads are missing, or whose
GDScript braces do not balance. This is not a parser of the full language;
it is the closure proof the projector needs.
"""
from __future__ import annotations

import re
from typing import Dict, List, Mapping, Tuple

_AUTOLOAD = re.compile(r'^([A-Za-z_][\w]*)="\*?([^"]+)"', re.M)
_EXT = re.compile(r'path="(res://[^"]+)"')
_PRELOAD = re.compile(r'preload\("(res://[^"]+)"\)')


def _balance(src: str) -> List[str]:
    problems = []
    # strip strings roughly so braces in text do not count
    stripped = re.sub(r'"(?:\\.|[^"\\])*"', '""', src)
    stripped = re.sub(r"'(?:\\.|[^'\\])*'", "''", stripped)
    for opener, closer, name in (("(", ")", "paren"), ("[", "]", "bracket"), ("{", "}", "brace")):
        if stripped.count(opener) != stripped.count(closer):
            problems.append(f"unbalanced {name}s")
    return problems


def check_files(files: Mapping[str, str]) -> List[str]:
    problems: List[str] = []
    keys = set(files)
    if "project.godot" not in keys:
        return ["missing project.godot"]
    godot = files["project.godot"]
    if "config_version=5" not in godot:
        problems.append("project.godot is not Godot 4 (config_version=5)")
    if 'run/main_scene=' not in godot:
        problems.append("no main scene")
    main = re.search(r'run/main_scene="([^"]+)"', godot)
    if main:
        rel = main.group(1).replace("res://", "")
        if rel not in keys:
            problems.append(f"main scene missing: {rel}")
    for name, path in _AUTOLOAD.findall(godot):
        rel = path.replace("res://", "").lstrip("*")
        if rel not in keys:
            problems.append(f"autoload {name} missing file {rel}")
    for rel, body in files.items():
        if not body.strip():
            problems.append(f"empty file {rel}")
        if rel.endswith(".gd"):
            problems.extend(f"{rel}: {p}" for p in _balance(body))
            if "extends " not in body.split("\n")[0] and "extends " not in "\n".join(body.split("\n")[:5]):
                problems.append(f"{rel}: no extends")
        for ref in list(_EXT.findall(body)) + list(_PRELOAD.findall(body)):
            target = ref.replace("res://", "")
            if target not in keys:
                problems.append(f"{rel} references missing {target}")
    required = (
        "scripts/autoloads/heat_system.gd",
        "scripts/autoloads/jeeves.gd",
        "scripts/player/player_controller.gd",
        "scripts/combat/enemy.gd",
    )
    for rel in required:
        if rel not in keys:
            problems.append(f"required {rel} missing")
    player = files.get("scripts/player/player_controller.gd", "")
    if "move_and_slide" not in player:
        problems.append("player never calls move_and_slide")
    if "HeatSystem" not in player:
        problems.append("player never talks to HeatSystem")
    return problems


def check_ok(files: Mapping[str, str]) -> Tuple[bool, List[str]]:
    problems = check_files(files)
    return not problems, problems
