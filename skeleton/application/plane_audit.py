"""Import-free structural audit for the organism, social, and galaxy planes.

F-15 grew three planes while earlier waves landed. This snapshot reports
export drift, genesis wiring, and boot-phase documentation without importing
those packages, so CLI/API consumers can inspect them the same way lifecycle
inspects capability readiness.
"""

from __future__ import annotations

import ast
from importlib.util import find_spec
from pathlib import Path
from typing import Final, Mapping

from .capability_manifest import CAPABILITY_MANIFEST_VERSION, get_capability


AUDITED_PLANE_IDS: Final[tuple[str, ...]] = ("organism", "social", "galaxy")
PLANE_AUDIT_KIND: Final = "plane_audit"


def _literal_str_list(node: ast.AST | None) -> list[str]:
    if not isinstance(node, (ast.List, ast.Tuple)):
        return []
    values: list[str] = []
    for element in node.elts:
        if isinstance(element, ast.Constant) and isinstance(element.value, str):
            values.append(element.value)
    return values


def _assigned_all(tree: ast.AST) -> list[str]:
    for node in tree.body if isinstance(tree, ast.Module) else []:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    return _literal_str_list(node.value)
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "__all__"
        ):
            return _literal_str_list(node.value)
    return []


def _module_init_path(module: str) -> Path | None:
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


def _public_exports(module: str) -> list[str]:
    init_path = _module_init_path(module)
    if init_path is None or not init_path.is_file():
        return []
    try:
        tree = ast.parse(init_path.read_text(encoding="utf-8"), filename=str(init_path))
    except (OSError, SyntaxError):
        return []
    return _assigned_all(tree)


def _architecture_exports(module: str) -> list[str]:
    from skeleton.architecture import get_package

    package = get_package(module) or {}
    exports = package.get("exports", [])
    if not isinstance(exports, list):
        return []
    return [item for item in exports if isinstance(item, str)]


def _boot_phase_modules() -> frozenset[str]:
    from skeleton.architecture import BOOT_PHASES

    modules: set[str] = set()
    for phase in BOOT_PHASES:
        phase_name = phase.get("phase")
        if isinstance(phase_name, str) and phase_name:
            modules.add(f"skeleton.{phase_name}")
        for subsystem in phase.get("subsystems", []):
            if not isinstance(subsystem, Mapping):
                continue
            module = subsystem.get("module")
            if isinstance(module, str) and module:
                modules.add(module)
    return frozenset(modules)


def _genesis_source_path() -> Path | None:
    spec = find_spec("skeleton.genesis")
    if spec is None or not spec.origin:
        return None
    path = Path(spec.origin)
    return path if path.is_file() else None


def _genesis_wire_map() -> dict[str, list[str]]:
    source = _genesis_source_path()
    if source is None:
        return {plane_id: [] for plane_id in AUDITED_PLANE_IDS}
    try:
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    except (OSError, SyntaxError):
        return {plane_id: [] for plane_id in AUDITED_PLANE_IDS}

    handles: dict[str, list[str]] = {plane_id: [] for plane_id in AUDITED_PLANE_IDS}
    seen: dict[str, set[str]] = {plane_id: set() for plane_id in AUDITED_PLANE_IDS}
    found: list[tuple[int, int, str, str]] = []
    for node in ast.walk(tree):
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
        phase = phase_node.value
        if phase not in handles:
            continue
        found.append((node.lineno, node.col_offset, phase, name_node.value))

    for _, _, phase, handle in sorted(found):
        if handle in seen[phase]:
            continue
        seen[phase].add(handle)
        handles[phase].append(handle)
    return handles


def _export_drift(public: list[str], documented: list[str]) -> dict[str, list[str]]:
    public_set = set(public)
    documented_set = set(documented)
    return {
        "missing_from_architecture": [name for name in public if name not in documented_set],
        "missing_from_public": [name for name in documented if name not in public_set],
    }


def _boot_phase_listed(module: str, boot_modules: frozenset[str]) -> bool:
    if module in boot_modules:
        return True
    prefix = f"{module}."
    return any(item == module or item.startswith(prefix) for item in boot_modules)


def plane_audit_snapshot() -> dict[str, object]:
    """Return a JSON-serializable F-15 plane audit without importing the planes."""

    wire_map = _genesis_wire_map()
    boot_modules = _boot_phase_modules()
    rows: list[dict[str, object]] = []
    for plane_id in AUDITED_PLANE_IDS:
        capability = get_capability(plane_id)
        public_exports = _public_exports(capability.module)
        architecture_exports = _architecture_exports(capability.module)
        handles = list(wire_map.get(plane_id, []))
        rows.append(
            {
                "id": capability.id,
                "module": capability.module,
                "description": capability.description,
                "resolvable": find_spec(capability.module) is not None,
                "public_exports": public_exports,
                "architecture_exports": architecture_exports,
                "export_drift": _export_drift(public_exports, architecture_exports),
                "genesis_wired": bool(handles),
                "genesis_handles": handles,
                "boot_phase_listed": _boot_phase_listed(capability.module, boot_modules),
            }
        )
    return {
        "schema_version": CAPABILITY_MANIFEST_VERSION,
        "kind": PLANE_AUDIT_KIND,
        "planes": rows,
    }
