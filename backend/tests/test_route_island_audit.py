"""Static guard against mountable FastAPI route islands.

A route module can compile and have tests while still being unreachable at runtime
if its module-level ``APIRouter`` is never added to the canonical registry.  This
check deliberately uses AST inspection rather than importing every route module,
so optional dependencies and module side effects do not distort the inventory.
"""
from __future__ import annotations

import ast
from pathlib import Path

from core.routes_registry import KNOWN_ROUTES, KNOWN_ROUTES_WITH_PREFIX

ROUTES_DIR = Path(__file__).resolve().parents[1] / "routes"

# Routers mounted deliberately outside the declarative registry.
# Keep this set tiny and explicit: every exception should have a visible mount
# site in core/routes_registry.py or server.py.
DIRECT_MOUNTS = {
    ("routes.registry_health", "router"),
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
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            if _call_name(node.value.func) != "APIRouter":
                continue
            for target in node.targets:
                if isinstance(target, ast.Name):
                    bindings.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.value, ast.Call):
            if _call_name(node.value.func) == "APIRouter" and isinstance(node.target, ast.Name):
                bindings.add(node.target.id)
    return bindings


def _declared_pairs() -> set[tuple[str, str]]:
    return {
        (entry[0], entry[1])
        for entry in (*KNOWN_ROUTES, *KNOWN_ROUTES_WITH_PREFIX)
    } | DIRECT_MOUNTS


def _discovered_pairs() -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for path in sorted(ROUTES_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        module = f"routes.{path.stem}"
        for attr in _router_bindings(path):
            pairs.add((module, attr))
    return pairs


def test_every_module_level_apirouter_is_reachable() -> None:
    missing = sorted(_discovered_pairs() - _declared_pairs())
    assert not missing, (
        "mountable route islands found; register them in core/routes_registry.py "
        "or document an explicit direct mount: "
        + ", ".join(f"{module}:{attr}" for module, attr in missing)
    )
