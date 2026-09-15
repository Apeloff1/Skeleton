"""Static ownership audit for FastAPI route modules.

A route module is considered integrated when its exported ``router`` is either:

* declared in ``core.routes_registry``; or
* imported by production code and passed to ``include_router`` (embedded
  sub-router ownership, e.g. Galaxy Studio decomposition modules).

The audit is intentionally AST-only. It never imports route modules, touches the
DB, or executes application code, so it is safe to run in lint/CI environments.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterable

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_ROUTES_DIR = _BACKEND_ROOT / "routes"
_REGISTRY_FILE = _BACKEND_ROOT / "core" / "routes_registry.py"


def _python_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*.py"):
        rel = path.relative_to(root)
        if "tests" in rel.parts or "__pycache__" in rel.parts:
            continue
        yield path


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _module_for_route_file(path: Path, routes_dir: Path = _ROUTES_DIR) -> str:
    rel = path.relative_to(routes_dir).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(("routes", *parts))


def _is_apirouter_ctor(node: ast.AST | None) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "APIRouter"
    return isinstance(func, ast.Attribute) and func.attr == "APIRouter"


def discover_router_modules(routes_dir: Path = _ROUTES_DIR) -> set[str]:
    """Return route modules that top-level-export ``router = APIRouter(...)``."""
    found: set[str] = set()
    if not routes_dir.exists():
        return found
    for path in routes_dir.rglob("*.py"):
        if path.name == "__init__.py":
            continue
        try:
            tree = _parse(path)
        except (OSError, SyntaxError, UnicodeError):
            continue
        for node in getattr(tree, "body", []):
            value: ast.AST | None = None
            target_name: str | None = None
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name):
                    target_name = target.id
                    value = node.value
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                target_name = node.target.id
                value = node.value
            if target_name == "router" and _is_apirouter_ctor(value):
                found.add(_module_for_route_file(path, routes_dir))
                break
    return found


def _registry_modules(registry_file: Path = _REGISTRY_FILE) -> set[str]:
    """Extract route module strings from the two declarative registry lists."""
    if not registry_file.exists():
        return set()
    tree = _parse(registry_file)
    result: set[str] = set()
    wanted = {"KNOWN_ROUTES", "KNOWN_ROUTES_WITH_PREFIX"}
    for node in getattr(tree, "body", []):
        name: str | None = None
        value: ast.AST | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            if isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
                value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
            value = node.value
        if name not in wanted or not isinstance(value, (ast.List, ast.Tuple)):
            continue
        for item in value.elts:
            if not isinstance(item, (ast.Tuple, ast.List)) or not item.elts:
                continue
            first = item.elts[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                result.add(first.value)
    return result


def _route_router_aliases(tree: ast.AST) -> tuple[dict[str, str], dict[str, str]]:
    """Return ``(router_alias -> module, module_alias -> module)`` mappings."""
    router_aliases: dict[str, str] = {}
    module_aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("routes."):
            for imported in node.names:
                if imported.name == "router":
                    router_aliases[imported.asname or imported.name] = node.module
        elif isinstance(node, ast.Import):
            for imported in node.names:
                if imported.name.startswith("routes."):
                    module_aliases[imported.asname or imported.name] = imported.name
    return router_aliases, module_aliases


def discover_embedded_router_modules(backend_root: Path = _BACKEND_ROOT) -> set[str]:
    """Find route modules whose router is passed to ``include_router`` elsewhere."""
    embedded: set[str] = set()
    if not backend_root.exists():
        return embedded
    for path in _python_files(backend_root):
        try:
            tree = _parse(path)
        except (OSError, SyntaxError, UnicodeError):
            continue
        router_aliases, module_aliases = _route_router_aliases(tree)
        if not router_aliases and not module_aliases:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == "include_router"):
                continue
            if not node.args:
                continue
            arg = node.args[0]
            if isinstance(arg, ast.Name):
                module = router_aliases.get(arg.id)
                if module:
                    embedded.add(module)
            elif isinstance(arg, ast.Attribute) and arg.attr == "router" and isinstance(arg.value, ast.Name):
                module = module_aliases.get(arg.value.id)
                if module:
                    embedded.add(module)
    return embedded


def build_route_island_report(
    *,
    backend_root: Path = _BACKEND_ROOT,
    routes_dir: Path | None = None,
    registry_file: Path | None = None,
) -> dict[str, tuple[str, ...]]:
    """Return deterministic ownership sets and the remaining route islands."""
    routes_dir = routes_dir or backend_root / "routes"
    registry_file = registry_file or backend_root / "core" / "routes_registry.py"
    routers = discover_router_modules(routes_dir)
    registered = _registry_modules(registry_file)
    embedded = discover_embedded_router_modules(backend_root)
    integrated = registered | embedded
    return {
        "routers": tuple(sorted(routers)),
        "registered": tuple(sorted(routers & registered)),
        "embedded": tuple(sorted(routers & embedded)),
        "islands": tuple(sorted(routers - integrated)),
    }


def route_islands() -> tuple[str, ...]:
    """Convenience accessor used by CI and diagnostics."""
    return build_route_island_report()["islands"]


__all__ = [
    "build_route_island_report",
    "discover_embedded_router_modules",
    "discover_router_modules",
    "route_islands",
]
