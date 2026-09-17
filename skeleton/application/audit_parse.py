"""Import-free AST helpers shared by structural application audits."""

from __future__ import annotations

import ast
from collections import defaultdict
from importlib.util import find_spec
from pathlib import Path
from typing import Mapping


def literal_str_list(node: ast.AST | None) -> list[str]:
    if not isinstance(node, (ast.List, ast.Tuple)):
        return []
    values: list[str] = []
    for element in node.elts:
        if isinstance(element, ast.Constant) and isinstance(element.value, str):
            values.append(element.value)
    return values


def assigned_all(tree: ast.AST) -> list[str]:
    for node in tree.body if isinstance(tree, ast.Module) else []:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    return literal_str_list(node.value)
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "__all__"
        ):
            return literal_str_list(node.value)
    return []


def module_init_path(module: str) -> Path | None:
    spec = find_spec(module)
    if spec is None:
        return None
    if spec.origin and spec.origin not in {"namespace", "built-in"}:
        origin = Path(spec.origin)
        if origin.name == "__init__.py":
            return origin
    locations = spec.submodule_search_locations
    if locations:
        candidate = Path(next(iter(locations))) / "__init__.py"
        if candidate.is_file():
            return candidate
    return None


def public_exports(module: str) -> list[str]:
    init_path = module_init_path(module)
    if init_path is None or not init_path.is_file():
        return []
    try:
        tree = ast.parse(init_path.read_text(encoding="utf-8"), filename=str(init_path))
    except (OSError, SyntaxError):
        return []
    return assigned_all(tree)


def architecture_exports(module: str) -> list[str]:
    from skeleton.architecture import get_package

    package = get_package(module) or {}
    exports = package.get("exports", [])
    if not isinstance(exports, list):
        return []
    return [item for item in exports if isinstance(item, str)]


def architecture_package_exists(module: str) -> bool:
    from skeleton.architecture import get_package

    return get_package(module) is not None


def export_drift(public: list[str], documented: list[str]) -> dict[str, list[str]]:
    public_set = set(public)
    documented_set = set(documented)
    return {
        "missing_from_architecture": [name for name in public if name not in documented_set],
        "missing_from_public": [name for name in documented if name not in public_set],
    }


def genesis_source_path() -> Path | None:
    spec = find_spec("skeleton.genesis")
    if spec is None or not spec.origin:
        return None
    path = Path(spec.origin)
    return path if path.is_file() else None


def parse_genesis_tree() -> ast.AST | None:
    source = genesis_source_path()
    if source is None:
        return None
    try:
        return ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    except (OSError, SyntaxError):
        return None


def genesis_boot_phase_order(tree: ast.AST | None = None) -> list[str]:
    parsed = tree if tree is not None else parse_genesis_tree()
    if parsed is None:
        return []
    for node in parsed.body if isinstance(parsed, ast.Module) else []:
        if not isinstance(node, ast.ClassDef) or node.name != "Genesis":
            continue
        for item in node.body:
            if not isinstance(item, ast.FunctionDef) or item.name != "boot":
                continue
            phases: list[str] = []
            for stmt in item.body:
                call = stmt.value if isinstance(stmt, ast.Expr) else None
                if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
                    continue
                attr = call.func.attr
                if attr.startswith("_phase_") and len(attr) > 7:
                    phases.append(attr[7:])
            return phases
    return []


def genesis_report_phases(tree: ast.AST | None = None) -> list[str]:
    parsed = tree if tree is not None else parse_genesis_tree()
    if parsed is None:
        return []
    found: list[tuple[int, int, str]] = []
    for node in ast.walk(parsed):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "append" or not node.args:
            continue
        receiver = node.func.value
        if not (
            isinstance(receiver, ast.Attribute)
            and receiver.attr == "phases"
            and isinstance(receiver.value, ast.Attribute)
            and receiver.value.attr == "report"
        ):
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            found.append((node.lineno, node.col_offset, arg.value))
    ordered: list[str] = []
    seen: set[str] = set()
    for _, _, phase in sorted(found):
        if phase in seen:
            continue
        seen.add(phase)
        ordered.append(phase)
    return ordered


def genesis_wire_map(tree: ast.AST | None = None) -> dict[str, list[str]]:
    parsed = tree if tree is not None else parse_genesis_tree()
    if parsed is None:
        return {}
    found: list[tuple[int, int, str, str]] = []
    for node in ast.walk(parsed):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "_wire" or len(node.args) < 2:
            continue
        phase_node, name_node = node.args[0], node.args[1]
        if not (
            isinstance(phase_node, ast.Constant)
            and isinstance(phase_node.value, str)
            and isinstance(name_node, ast.Constant)
            and isinstance(name_node.value, str)
        ):
            continue
        found.append((node.lineno, node.col_offset, phase_node.value, name_node.value))
    handles: dict[str, list[str]] = {}
    seen: dict[str, set[str]] = defaultdict(set)
    for _, _, phase, handle in sorted(found):
        handles.setdefault(phase, [])
        if handle in seen[phase]:
            continue
        seen[phase].add(handle)
        handles[phase].append(handle)
    return handles


def boot_phase_catalog() -> dict[str, list[str]]:
    from skeleton.architecture import BOOT_PHASES

    catalog: dict[str, list[str]] = {}
    for phase in BOOT_PHASES:
        name = phase.get("phase")
        if not isinstance(name, str) or not name:
            continue
        subsystems: list[str] = []
        for subsystem in phase.get("subsystems", []):
            if not isinstance(subsystem, Mapping):
                continue
            subsystem_name = subsystem.get("name")
            if isinstance(subsystem_name, str) and subsystem_name:
                subsystems.append(subsystem_name)
        catalog[name] = subsystems
    return catalog
