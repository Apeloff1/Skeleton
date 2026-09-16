"""Fail closed on runtime-selected Python module imports in backend production code.

Literal module names remain allowed. Runtime-selected module names must normally be
replaced with an explicit allowlist/dispatch table so untrusted input cannot choose
import execution paths.

A small number of legacy internal loaders are temporarily retained behind exact,
time-bounded exceptions. Exceptions bind the repository path, enclosing function,
import primitive, and name expression; widening or moving a loader therefore fails
closed. Expired exceptions fail exactly like any other dynamic import.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import date
import os
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


@dataclass(frozen=True)
class DynamicImportException:
    """One narrow, temporary exception for an audited internal loader."""

    function: str
    primitive: str
    name_expression: str
    expires_on: date
    rationale: str


# These are migration debt, not permanent policy exemptions. Each entry is exact
# enough that adding another dynamic import to the same file/function with a
# different expression or primitive still fails the gate.
APPROVED_DYNAMIC_IMPORT_EXCEPTIONS: dict[str, tuple[DynamicImportException, ...]] = {
    "backend/core/routes_registry.py": (
        DynamicImportException(
            function="register_routes",
            primitive="importlib.import_module",
            name_expression="module_path",
            expires_on=date(2026, 12, 31),
            rationale="Declarative router registry; module names come from repository-owned route tables.",
        ),
    ),
    "backend/routes/gameforge_studio.py": (
        DynamicImportException(
            function="_try",
            primitive="__import__",
            name_expression="path",
            expires_on=date(2026, 12, 31),
            rationale="Studio startup passes repository-owned literal module names into this defensive loader.",
        ),
    ),
    "backend/server.py": (
        DynamicImportException(
            function="_kick_agent_knowledge",
            primitive="__import__",
            name_expression="f'seeds.{mod}'",
            expires_on=date(2026, 12, 31),
            rationale="Background seeding iterates a repository-owned literal seed-module table.",
        ),
    ),
}


class DynamicImportScanError(RuntimeError):
    """Raised when the scanner cannot prove complete source discovery."""


def python_files(root: Path | None = None) -> Iterable[Path]:
    """Yield backend Python sources without following symlinks.

    Security gates must not silently lose coverage when a directory cannot be
    enumerated, so traversal errors are converted into one stable scanner error
    and handled as a hard failure by ``main``.
    """
    scan_root = BACKEND_ROOT if root is None else root
    files: list[Path] = []
    pending = [scan_root]

    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as iterator:
                entries = sorted(iterator, key=lambda entry: entry.name)
        except OSError as exc:
            raise DynamicImportScanError("source traversal failed") from exc

        child_dirs: list[Path] = []
        for entry in entries:
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if entry.name not in SKIP_DIRS:
                        child_dirs.append(Path(entry.path))
                    continue
                if entry.is_file(follow_symlinks=False) and entry.name.endswith(".py"):
                    files.append(Path(entry.path))
            except OSError as exc:
                raise DynamicImportScanError("source traversal failed") from exc

        pending.extend(reversed(child_dirs))

    yield from sorted(files)


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


def _literal_text(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


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
    """Conservatively follow simple module/callable aliases to import primitives."""
    for _ in range(6):
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
                value,
                importlib_modules,
                builtins_modules,
                function_aliases,
            )
            if primitive is None:
                continue
            for target in targets:
                if function_aliases.get(target) == primitive:
                    continue
                function_aliases[target] = primitive
                changed = True
        if not changed:
            return


def _called_dynamic_import(
    node: ast.Call,
    importlib_modules: set[str],
    builtins_modules: set[str],
    function_aliases: dict[str, str],
) -> str | None:
    return _dynamic_import_callable(
        node.func,
        importlib_modules,
        builtins_modules,
        function_aliases,
    )


def _parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}


def _enclosing_function(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str:
    current = node
    while current in parents:
        current = parents[current]
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current.name
    return "<module>"


def _approved_exception(
    path: Path,
    node: ast.Call,
    primitive: str,
    name: ast.AST | None,
    parents: dict[ast.AST, ast.AST],
) -> bool:
    if name is None:
        return False
    key = display_path(path).as_posix()
    specs = APPROVED_DYNAMIC_IMPORT_EXCEPTIONS.get(key, ())
    if not specs:
        return False
    function = _enclosing_function(node, parents)
    expression = ast.unparse(name)
    today = date.today()
    return any(
        spec.function == function
        and spec.primitive == primitive
        and spec.name_expression == expression
        and spec.expires_on >= today
        and bool(spec.rationale.strip())
        for spec in specs
    )


def violations(path: Path) -> list[str]:
    label = display_path(path)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        return [f"{label}: parse failure: {type(exc).__name__}"]

    importlib_modules, builtins_modules, function_aliases = _import_aliases(tree)
    _propagate_aliases(tree, importlib_modules, builtins_modules, function_aliases)
    parents = _parent_map(tree)
    findings: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        primitive = _called_dynamic_import(
            node,
            importlib_modules,
            builtins_modules,
            function_aliases,
        )
        if primitive is None:
            continue
        name = _call_name_argument(node)
        if _literal_module_name(name):
            continue
        if _approved_exception(path, node, primitive, name, parents):
            continue
        findings.append(
            f"{label}:{node.lineno}: {primitive}() module name must be a non-empty literal string; "
            "use an explicit allowlist/dispatch table for runtime selection"
        )
    return findings


def main() -> int:
    findings: list[str] = []
    try:
        paths = list(python_files())
    except DynamicImportScanError as exc:
        print("Dynamic import safety violations detected:", file=sys.stderr)
        print(f"  - scanner coverage failure: {exc}", file=sys.stderr)
        return 1

    scanned = len(paths)
    for path in paths:
        findings.extend(violations(path))
    if scanned == 0:
        findings.append("scanner coverage failure: no backend Python files were scanned")
    if findings:
        print("Dynamic import safety violations detected:", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        return 1
    print(f"Dynamic import safety gate passed across {scanned} backend Python files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
