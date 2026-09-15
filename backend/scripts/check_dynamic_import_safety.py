"""Fail closed on runtime-selected Python module imports in backend production code.

Literal module names remain allowed. Runtime-selected module names must be replaced
with an explicit allowlist/dispatch table so untrusted input cannot choose import
execution paths.
"""
from __future__ import annotations

import ast
from pathlib import Path
import sys
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".expo",
    "coverage",
    "tests",
}


def python_files() -> Iterable[Path]:
    for path in BACKEND_ROOT.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def display_path(path: Path) -> Path:
    try:
        return path.relative_to(REPO_ROOT)
    except ValueError:
        return path


def _literal_module_name(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str) and bool(node.value.strip())


def _call_name_argument(node: ast.Call) -> ast.AST | None:
    if node.args:
        return node.args[0]
    for keyword in node.keywords:
        if keyword.arg == "name":
            return keyword.value
    return None


def _importlib_aliases(tree: ast.AST) -> tuple[set[str], set[str]]:
    module_aliases: set[str] = set()
    function_aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                if item.name == "importlib":
                    module_aliases.add(item.asname or "importlib")
        elif isinstance(node, ast.ImportFrom) and node.module == "importlib":
            for item in node.names:
                if item.name == "import_module":
                    function_aliases.add(item.asname or item.name)
    return module_aliases, function_aliases


def _called_dynamic_import(node: ast.Call, module_aliases: set[str], function_aliases: set[str]) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        if func.id == "__import__":
            return "__import__"
        if func.id in function_aliases:
            return "importlib.import_module"
        return None
    if (
        isinstance(func, ast.Attribute)
        and func.attr == "import_module"
        and isinstance(func.value, ast.Name)
        and func.value.id in module_aliases
    ):
        return "importlib.import_module"
    return None


def violations(path: Path) -> list[str]:
    label = display_path(path)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        return [f"{label}: parse failure: {exc}"]

    module_aliases, function_aliases = _importlib_aliases(tree)
    findings: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        primitive = _called_dynamic_import(node, module_aliases, function_aliases)
        if primitive is None:
            continue
        name = _call_name_argument(node)
        if not _literal_module_name(name):
            findings.append(
                f"{label}:{node.lineno}: {primitive}() module name must be a non-empty literal string; "
                "use an explicit allowlist/dispatch table for runtime selection"
            )
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
