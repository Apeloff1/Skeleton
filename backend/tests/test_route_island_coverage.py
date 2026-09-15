"""Static guard against mountable FastAPI route islands.

The audit is AST-only so route discovery never imports application modules or
triggers optional dependency/startup side effects.  Every module-level
``APIRouter`` binding must be present in the canonical registry, explicitly
mounted elsewhere, or deliberately retired with a documented replacement.
"""
from __future__ import annotations

import ast
from pathlib import Path

from core.routes_registry import KNOWN_ROUTES, KNOWN_ROUTES_WITH_PREFIX


ROUTES_DIR = Path(__file__).resolve().parents[1] / "routes"

# Routers mounted deliberately outside the declarative registry.
DIRECT_MOUNTS = {
    ("routes.registry_health", "router"),
}

# ``academy.py`` is the retired in-memory v2 surface. ``academy_v3.py`` owns
# the same /api/academy prefix and is the registered MongoDB-backed successor;
# mounting both would create ambiguous duplicate routes rather than reconnect
# useful functionality.
INTENTIONAL_UNMOUNTED = {
    ("routes.academy", "router"),
}


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _router_bindings(path: Path) -> set[str]:
    """Return module-level names directly bound to ``APIRouter(...)`` calls."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    bindings: set[str] = set()
    for node in tree.body:
        value = None
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            value = node.value
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            value = node.value
            targets = [node.target]
        if not isinstance(value, ast.Call) or _call_name(value.func) != "APIRouter":
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                bindings.add(target.id)
    return bindings


def _declared_pairs() -> set[tuple[str, str]]:
    return {
        (entry[0], entry[1])
        for entry in (*KNOWN_ROUTES, *KNOWN_ROUTES_WITH_PREFIX)
    } | DIRECT_MOUNTS | INTENTIONAL_UNMOUNTED


def _discovered_pairs() -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for path in sorted(ROUTES_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        module = f"routes.{path.stem}"
        pairs.update((module, attr) for attr in _router_bindings(path))
    return pairs


def test_every_module_level_apirouter_is_accounted_for() -> None:
    missing = sorted(_discovered_pairs() - _declared_pairs())
    assert not missing, (
        "mountable route islands are missing from core.routes_registry or an "
        "explicit mount/retirement classification: "
        + ", ".join(f"{module}:{attr}" for module, attr in missing)
    )
