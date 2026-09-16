from __future__ import annotations

import ast
from pathlib import Path

from core.routes_registry import KNOWN_ROUTES, KNOWN_ROUTES_WITH_PREFIX


ROUTES_DIR = Path(__file__).resolve().parents[1] / "routes"
SPECIAL_MOUNTS = {"routes.registry_health"}
# ``academy.py`` is the retired in-memory v2 surface. ``academy_v3.py`` owns
# the same /api/academy prefix and is the registered MongoDB-backed successor;
# mounting both would create ambiguous duplicate routes rather than reconnect
# useful functionality.
INTENTIONAL_UNMOUNTED = {"routes.academy"}


def _internally_mounted_modules() -> set[str]:
    """Discover child routers mounted by another route module.

    Decomposed route families such as ``routes.galaxy_studio`` intentionally
    include their child routers themselves because Starlette route ordering is
    part of their public contract. Registering those children again through
    ``core.routes_registry`` would duplicate paths and can change which static
    route wins over a dynamic parameter route. Keep this audit AST-only while
    treating a concrete ``from routes.x import router as y`` followed by
    ``*.include_router(y)`` as an accounted-for mount.
    """
    mounted: set[str] = set()
    for path in sorted(ROUTES_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported_router_aliases: dict[str, str] = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if not node.module or not node.module.startswith("routes."):
                continue
            for imported in node.names:
                if imported.name == "router":
                    imported_router_aliases[imported.asname or imported.name] = node.module

        if not imported_router_aliases:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute) or func.attr != "include_router":
                continue
            if not node.args or not isinstance(node.args[0], ast.Name):
                continue
            module = imported_router_aliases.get(node.args[0].id)
            if module:
                mounted.add(module)
    return mounted


def _declared_modules() -> set[str]:
    return {
        entry[0]
        for entry in (*KNOWN_ROUTES, *KNOWN_ROUTES_WITH_PREFIX)
    } | SPECIAL_MOUNTS | INTENTIONAL_UNMOUNTED | _internally_mounted_modules()


def _defines_api_router(path: Path) -> bool:
    """Return True when a module defines its public ``router`` as APIRouter.

    This is intentionally AST-only: discovery must not import route modules or
    trigger their startup side effects just to audit registration coverage.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        value = None
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            value = node.value
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            value = node.value
            targets = [node.target]
        if value is None or not isinstance(value, ast.Call):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "router"
            for target in targets
        ):
            continue
        func = value.func
        if isinstance(func, ast.Name) and func.id == "APIRouter":
            return True
        if isinstance(func, ast.Attribute) and func.attr == "APIRouter":
            return True
    return False


def test_every_top_level_api_router_is_accounted_for() -> None:
    declared = _declared_modules()
    islands = []
    for path in sorted(ROUTES_DIR.glob("*.py")):
        if path.name == "__init__.py" or not _defines_api_router(path):
            continue
        module = f"routes.{path.stem}"
        if module not in declared:
            islands.append(module)

    assert not islands, (
        "mountable route islands are missing from registry or parent-router mounts: "
        + ", ".join(islands)
    )
