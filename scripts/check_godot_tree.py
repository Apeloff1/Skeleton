#!/usr/bin/env python3
"""Static check that a directory is a runnable-shaped Godot 4 project tree.

Usage::

    python scripts/check_godot_tree.py TREE_DIR [--json] [--min-scenes 1]

Checks (no Godot binary needed):

* ``project.godot`` exists and declares ``config_version=``;
* ``run/main_scene`` (if set) and every ``[autoload]`` script resolve;
* at least ``--min-scenes`` ``.tscn`` scenes exist;
* every ``[ext_resource ... path="res://..."]`` in ``.tscn``/``.tres`` exists, and
  ``type="Script"`` resources point at an existing ``.gd`` file;
* every literal ``res://`` reference in project text files resolves to a file
  (or directory, for refs ending in ``/``); refs built at runtime (containing
  ``%``, ``{`` or ``+``) are counted as dynamic and not resolved;
* no ``res://`` reference escapes the tree (``..``).

Prints a summary with elapsed ms. Exits 0 when clean, 1 on problems, 2 on usage.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional

EXIT_OK, EXIT_FAIL, EXIT_USAGE = 0, 1, 2
TEXT_SUFFIXES = {".godot", ".tscn", ".tres", ".gd", ".cfg", ".gdshader"}
MAX_TEXT_BYTES = 4 * 1024 * 1024

RES_REF = re.compile(r"res://[^\s\"'()\[\]\\,;]*")
EXT_RESOURCE = re.compile(r"^\[ext_resource\b([^\]]*)\]", re.MULTILINE)
ATTR = re.compile(r'(\w+)="([^"]*)"')
SECTION = re.compile(r"^\[([^\]]+)\]\s*$")
DYNAMIC_MARKERS = ("%", "{", "+")


def _is_dynamic(ref: str, after: str) -> bool:
    """A ref assembled at runtime: ``"res://x/%s.tscn" % n`` or ``"res://x/" + n``."""
    if any(marker in ref for marker in DYNAMIC_MARKERS):
        return True
    rest = after[1:].lstrip() if after[:1] in ("\"", "'") else ""
    return rest.startswith(("%", "+"))


def _res_to_path(root: Path, ref: str) -> Optional[Path]:
    rel = ref[len("res://"):]
    parts = PurePosixPath(rel).parts if rel else ()
    if ".." in parts:
        return None
    return root.joinpath(*parts)


def _project_sections(text: str) -> Dict[str, Dict[str, str]]:
    sections: Dict[str, Dict[str, str]] = {}
    current = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(";"):
            continue
        m = SECTION.match(line)
        if m:
            current = m.group(1)
            sections.setdefault(current, {})
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            sections.setdefault(current, {})[key.strip()] = value.strip()
    return sections


def check_tree(root: Path, *, min_scenes: int = 1) -> Dict[str, Any]:
    root = Path(root)
    problems: List[str] = []
    report: Dict[str, Any] = {"root": str(root), "problems": problems}
    if not root.is_dir():
        problems.append(f"tree dir does not exist: {root}")
        report["ok"] = False
        return report

    files = sorted(p for p in root.rglob("*") if p.is_file())
    rel = lambda p: p.relative_to(root).as_posix()  # noqa: E731
    scenes = [rel(p) for p in files if p.suffix == ".tscn"]
    scripts = [rel(p) for p in files if p.suffix == ".gd"]
    report.update(files=len(files), scenes=scenes, scripts=len(scripts))

    project = root / "project.godot"
    if not project.is_file():
        problems.append("missing project.godot")
    else:
        text = project.read_text(encoding="utf-8", errors="replace")
        if "config_version=" not in text:
            problems.append("project.godot has no config_version=")
        sections = _project_sections(text)
        main_scene = sections.get("application", {}).get("run/main_scene", "").strip('"')
        report["main_scene"] = main_scene or None
        if main_scene:
            target = _res_to_path(root, main_scene) if main_scene.startswith("res://") else None
            if target is None or not target.is_file():
                problems.append(f"run/main_scene does not resolve: {main_scene}")
        autoloads = sections.get("autoload", {})
        report["autoloads"] = len(autoloads)
        for name, value in sorted(autoloads.items()):
            ref = value.strip('"').lstrip("*")
            target = _res_to_path(root, ref) if ref.startswith("res://") else None
            if target is None or not target.is_file():
                problems.append(f"autoload {name} does not resolve: {ref}")

    if len(scenes) < min_scenes:
        problems.append(f"expected at least {min_scenes} .tscn scene(s), found {len(scenes)}")

    ext_count = 0
    for path in files:
        if path.suffix not in (".tscn", ".tres"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in EXT_RESOURCE.finditer(text):
            attrs = dict(ATTR.findall(m.group(1)))
            ref = attrs.get("path", "")
            ext_count += 1
            if not ref.startswith("res://"):
                problems.append(f"{rel(path)}: ext_resource without res:// path: {m.group(0)}")
                continue
            target = _res_to_path(root, ref)
            if target is None or not target.is_file():
                problems.append(f"{rel(path)}: missing ext_resource {ref}")
            elif attrs.get("type") == "Script" and target.suffix != ".gd":
                problems.append(f"{rel(path)}: Script ext_resource is not a .gd file: {ref}")
    report["ext_resources"] = ext_count

    ref_count = dynamic = 0
    for path in files:
        if path.suffix not in TEXT_SUFFIXES or path.stat().st_size > MAX_TEXT_BYTES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in RES_REF.finditer(text):
            ref = m.group(0)
            if ref.startswith("res://.godot/"):
                continue  # editor import cache, regenerated by Godot
            if _is_dynamic(ref, text[m.end():m.end() + 4]):
                dynamic += 1
                continue
            ref_count += 1
            target = _res_to_path(root, ref)
            if target is None:
                problems.append(f"{rel(path)}: res:// reference escapes the tree: {ref}")
            elif ref.endswith("/") or ref == "res://":
                if not target.is_dir():
                    problems.append(f"{rel(path)}: missing directory {ref}")
            elif not target.is_file():
                problems.append(f"{rel(path)}: missing res:// reference {ref}")
    report.update(res_refs=ref_count, dynamic_refs=dynamic)
    report["ok"] = not problems
    return report


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check a Godot project tree")
    parser.add_argument("tree_dir")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--min-scenes", type=int, default=1)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return EXIT_USAGE if exc.code else EXIT_OK
    t0 = time.perf_counter()
    report = check_tree(Path(args.tree_dir), min_scenes=max(0, args.min_scenes))
    report["elapsed_ms"] = int(round((time.perf_counter() - t0) * 1000))
    if args.json:
        print(json.dumps(report, sort_keys=True))
    else:
        verdict = "PASS" if report["ok"] else "FAIL"
        print(
            f"{verdict} godot tree {report['root']}: files={report.get('files', 0)} "
            f"scenes={len(report.get('scenes') or [])} scripts={report.get('scripts', 0)} "
            f"autoloads={report.get('autoloads', 0)} ext_resources={report.get('ext_resources', 0)} "
            f"res_refs={report.get('res_refs', 0)} dynamic_refs={report.get('dynamic_refs', 0)} "
            f"main_scene={report.get('main_scene')} [budget] {report['elapsed_ms']} ms"
        )
        for problem in report["problems"]:
            print(f"  - {problem}")
    return EXIT_OK if report["ok"] else EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
