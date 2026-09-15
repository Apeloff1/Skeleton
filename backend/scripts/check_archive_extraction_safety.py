"""Fail closed on unsafe tar archive extraction in backend production code.

Python 3.11 tarfile extraction accepts archive-controlled paths and link targets
unless a restrictive extraction filter is supplied. Canonical backend code must
therefore use the `data` filter explicitly for every TarFile.extract()/extractall()
operation. This scanner is dependency-free so it can run in the early security
quality gate.
"""
from __future__ import annotations

import ast
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
import sys

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
    "tests",
}
PYTHON_SCOPES = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
TARFILE_CONSTRUCTORS = {"tarfile.open", "tarfile.TarFile", "tarfile.TarFile.open"}
TARFILE_EXTRACTION_CALLS = {"tarfile.TarFile.extract", "tarfile.TarFile.extractall"}


def production_python_files() -> Iterable[Path]:
    if not BACKEND_ROOT.exists():
        return
    for path in BACKEND_ROOT.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def display_path(path: Path) -> Path:
    try:
        return path.relative_to(REPO_ROOT)
    except ValueError:
        return path


def dotted_name(node: ast.AST) -> str | None:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return ".".join(reversed(parts))
    return None


def import_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                if item.name == "tarfile":
                    aliases[item.asname or item.name] = "tarfile"
        elif isinstance(node, ast.ImportFrom) and node.module == "tarfile":
            for item in node.names:
                if item.name != "*":
                    aliases[item.asname or item.name] = f"tarfile.{item.name}"
    return aliases


def canonical_name(node: ast.AST, aliases: dict[str, str]) -> str | None:
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Call):
        owner = canonical_name(node.value.func, aliases)
        if owner:
            if owner in TARFILE_CONSTRUCTORS:
                owner = "tarfile.TarFile"
            return f"{owner}.{node.attr}"

    name = dotted_name(node)
    if not name:
        return None
    root, dot, suffix = name.partition(".")
    replacement = aliases.get(root)
    if replacement is None:
        return name
    return replacement + (f".{suffix}" if dot else "")


def _scope_nodes(scope: ast.AST) -> Iterable[ast.AST]:
    def descend(node: ast.AST) -> Iterable[ast.AST]:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, PYTHON_SCOPES):
                continue
            yield child
            yield from descend(child)

    yield from descend(scope)


def _target_names(target: ast.AST | None) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        names: set[str] = set()
        for item in target.elts:
            names.update(_target_names(item))
        return names
    return set()


def _parameter_names(scope: ast.AST) -> set[str]:
    if not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        return set()
    args = scope.args
    names = {arg.arg for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs)}
    if args.vararg:
        names.add(args.vararg.arg)
    if args.kwarg:
        names.add(args.kwarg.arg)
    return names


def _tarfile_bindings(scope: ast.AST, aliases: dict[str, str]) -> dict[str, str]:
    """Infer stable names bound directly to a TarFile instance."""
    nodes = list(_scope_nodes(scope))
    stores = Counter(
        node.id
        for node in nodes
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
    )
    candidates: set[str] = set()

    for node in nodes:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if isinstance(value, ast.Call) and canonical_name(value.func, aliases) in TARFILE_CONSTRUCTORS:
                for target in targets:
                    candidates.update(_target_names(target))
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if (
                    isinstance(item.context_expr, ast.Call)
                    and canonical_name(item.context_expr.func, aliases) in TARFILE_CONSTRUCTORS
                ):
                    candidates.update(_target_names(item.optional_vars))

    parameters = _parameter_names(scope)
    return {
        name: "tarfile.TarFile"
        for name in candidates
        if stores[name] == 1 and name not in parameters
    }


def _keyword(node: ast.Call, name: str) -> ast.AST | None:
    for keyword in node.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _uses_data_filter(node: ast.Call, aliases: dict[str, str]) -> bool:
    value = _keyword(node, "filter")
    if isinstance(value, ast.Constant) and value.value == "data":
        return True
    return value is not None and canonical_name(value, aliases) == "tarfile.data_filter"


def call_violation(node: ast.Call, aliases: dict[str, str]) -> str | None:
    name = canonical_name(node.func, aliases)
    if name not in TARFILE_EXTRACTION_CALLS:
        return None
    if _uses_data_filter(node, aliases):
        return None
    return (
        f"{name}() must use filter='data' (or tarfile.data_filter) to block "
        "archive path/link traversal"
    )


def violations(path: Path) -> list[str]:
    label = display_path(path)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        return [f"{label}: parse failure: {exc}"]

    import_map = import_aliases(tree)
    findings: list[str] = []
    scopes = [node for node in ast.walk(tree) if isinstance(node, PYTHON_SCOPES)]
    for scope in scopes:
        aliases = {**import_map, **_tarfile_bindings(scope, import_map)}
        for node in _scope_nodes(scope):
            if not isinstance(node, ast.Call):
                continue
            violation = call_violation(node, aliases)
            if violation:
                findings.append(f"{label}:{node.lineno}: {violation}")
    return findings


def repository_violations() -> list[str]:
    findings: list[str] = []
    files = list(production_python_files())
    if not files:
        return ["no backend production Python files found"]
    for path in files:
        findings.extend(violations(path))
    return findings


def main() -> int:
    findings = repository_violations()
    if findings:
        print("Unsafe tar archive extraction detected:", file=sys.stderr)
        for finding in sorted(findings):
            print(f"  - {finding}", file=sys.stderr)
        return 1
    print("Archive extraction safety gate passed: all tar extraction uses the data filter.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
