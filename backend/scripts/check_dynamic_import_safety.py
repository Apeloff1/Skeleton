"""Fail closed on runtime-selected Python module imports in backend production code.

Literal absolute module names remain allowed. Runtime-selected module names,
callable aliases, and runtime-selected relative-import context must use an
explicit allowlist/dispatch table so untrusted input cannot choose import paths.
"""
from __future__ import annotations

import ast
from pathlib import Path
import sys
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
SKIP_DIRS = {
    ".git", ".venv", "venv", "__pycache__", "node_modules", "dist", "build",
    ".next", ".expo", "coverage", "tests",
}


def python_files() -> Iterable[Path]:
    for path in BACKEND_ROOT.rglob("*.py"):
        if not any(part in SKIP_DIRS for part in path.parts):
            yield path


def display_path(path: Path) -> Path:
    try:
        return path.relative_to(REPO_ROOT)
    except ValueError:
        return path


def _literal_text(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        value = node.value.strip()
        return value or None
    return None


def _argument(node: ast.Call, position: int, keyword_name: str) -> ast.AST | None:
    if len(node.args) > position:
        return node.args[position]
    for keyword in node.keywords:
        if keyword.arg == keyword_name:
            return keyword.value
    return None


def _import_aliases(tree: ast.AST) -> tuple[set[str], set[str], dict[str, str]]:
    importlib_modules: set[str] = set()
    builtins_modules: set[str] = set()
    function_aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                if item.name == "importlib":
                    importlib_modules.add(item.asname or "importlib")
                elif item.name == "builtins":
                    builtins_modules.add(item.asname or "builtins")
        elif isinstance(node, ast.ImportFrom):
            if node.module == "importlib":
                for item in node.names:
                    if item.name == "import_module":
                        function_aliases[item.asname or item.name] = "importlib.import_module"
            elif node.module == "builtins":
                for item in node.names:
                    if item.name == "__import__":
                        function_aliases[item.asname or item.name] = "__import__"
    return importlib_modules, builtins_modules, function_aliases


def _dynamic_import_callable(
    node: ast.AST,
    importlib_modules: set[str],
    builtins_modules: set[str],
    function_aliases: dict[str, str],
) -> str | None:
    if isinstance(node, ast.Name):
        if node.id == "__import__":
            return "__import__"
        return function_aliases.get(node.id)
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        if node.attr == "import_module" and node.value.id in importlib_modules:
            return "importlib.import_module"
        if node.attr == "__import__" and (
            node.value.id in builtins_modules or node.value.id == "__builtins__"
        ):
            return "__import__"
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
        if node.value.id == "__builtins__" and _literal_text(node.slice) == "__import__":
            return "__import__"
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        and len(node.args) >= 2
        and isinstance(node.args[0], ast.Name)
    ):
        owner = node.args[0].id
        attribute = _literal_text(node.args[1])
        if owner in importlib_modules and attribute == "import_module":
            return "importlib.import_module"
        if (owner in builtins_modules or owner == "__builtins__") and attribute == "__import__":
            return "__import__"
    return None


def _target_names(target: ast.AST) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        names: set[str] = set()
        for item in target.elts:
            names.update(_target_names(item))
        return names
    return set()


def _assignment_pairs(tree: ast.AST) -> Iterable[tuple[set[str], ast.AST]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            names: set[str] = set()
            for target in node.targets:
                names.update(_target_names(target))
            if names:
                yield names, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            names = _target_names(node.target)
            if names:
                yield names, node.value
        elif isinstance(node, ast.NamedExpr):
            names = _target_names(node.target)
            if names:
                yield names, node.value


def _propagate_aliases(
    tree: ast.AST,
    importlib_modules: set[str],
    builtins_modules: set[str],
    function_aliases: dict[str, str],
) -> None:
    """Conservatively follow simple aliases until the finite alias sets stop growing."""
    while True:
        changed = False
        for targets, value in _assignment_pairs(tree):
            if isinstance(value, ast.Name):
                if value.id in importlib_modules:
                    before = len(importlib_modules)
                    importlib_modules.update(targets)
                    changed |= len(importlib_modules) != before
                    continue
                if value.id in builtins_modules:
                    before = len(builtins_modules)
                    builtins_modules.update(targets)
                    changed |= len(builtins_modules) != before
                    continue
            primitive = _dynamic_import_callable(
                value, importlib_modules, builtins_modules, function_aliases
            )
            if primitive is None:
                continue
            for target in targets:
                if function_aliases.get(target) != primitive:
                    function_aliases[target] = primitive
                    changed = True
        if not changed:
            return


def _call_violation(
    node: ast.Call,
    importlib_modules: set[str],
    builtins_modules: set[str],
    function_aliases: dict[str, str],
) -> str | None:
    primitive = _dynamic_import_callable(
        node.func, importlib_modules, builtins_modules, function_aliases
    )
    if primitive is None:
        return None
    name = _literal_text(_argument(node, 0, "name"))
    if name is None:
        return (
            f"{primitive}() module name must be a non-empty literal string; "
            "use an explicit allowlist/dispatch table for runtime selection"
        )
    if primitive == "importlib.import_module" and name.startswith("."):
        if _literal_text(_argument(node, 1, "package")) is None:
            return (
                "importlib.import_module() relative import package must be a non-empty "
                "literal string; use an explicit allowlist/dispatch table"
            )
    if primitive == "__import__":
        level = _argument(node, 4, "level")
        if level is not None and not (
            isinstance(level, ast.Constant)
            and type(level.value) is int
            and level.value == 0
        ):
            return "__import__() relative import level must be literal 0"
    return None


def violations(path: Path) -> list[str]:
    label = display_path(path)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        return [f"{label}: parse failure: {exc}"]
    importlib_modules, builtins_modules, function_aliases = _import_aliases(tree)
    _propagate_aliases(tree, importlib_modules, builtins_modules, function_aliases)
    findings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            violation = _call_violation(
                node, importlib_modules, builtins_modules, function_aliases
            )
            if violation:
                findings.append(f"{label}:{node.lineno}: {violation}")
    return findings


def main() -> int:
    findings: list[str] = []
    for path in python_files():
        findings.extend(violations(path))
    if findings:
        print("Dynamic import safety violations detected:", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        return 1
    print("Dynamic import safety gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
