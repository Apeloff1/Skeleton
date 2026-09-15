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


def _declared_modules() -> set[str]:
    return {
        entry[0]
        for entry in (*KNOWN_ROUTES, *KNOWN_ROUTES_WITH_PREFIX)
    } | SPECIAL_MOUNTS | INTENTIONAL_UNMOUNTED


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
        "mountable route islands are missing from core.routes_registry: "
        + ", ".join(islands)
    )
