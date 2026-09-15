"""Fail closed on unsafe tar archive extraction in backend production code.

Python 3.11 tarfile extraction accepts archive-controlled paths and link targets
unless a restrictive extraction filter is supplied. Canonical backend code must
therefore use the `data` filter explicitly for every TarFile.extract()/extractall()
operation. This scanner is dependency-free so it can run in the early security
quality gate.
"""
from __future__ import annotations

import ast
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
TARFILE_SAFE_CALLABLES = TARFILE_CONSTRUCTORS | TARFILE_EXTRACTION_CALLS | {"tarfile.data_filter"}


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

    # Prefer the longest exact/prefix binding so instance attributes such as
    # ``holder.archive.extractall`` can resolve through ``holder.archive``
    # before a shorter import alias is considered.
    for alias in sorted(aliases, key=len, reverse=True):
        if name == alias:
            return aliases[alias]
        prefix = alias + "."
        if name.startswith(prefix):
            return aliases[alias] + name[len(alias) :]
    return name


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
    if isinstance(target, ast.Attribute):
        name = dotted_name(target)
        return {name} if name else set()
    if isinstance(target, (ast.Tuple, ast.List)):
        names: set[str] = set()
        for item in target.elts:
            names.update(_target_names(item))
        return names
    return set()


def _assignment_pairs(scope: ast.AST) -> Iterable[tuple[set[str], ast.AST]]:
    for node in _scope_nodes(scope):
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


def _callable_aliases(scope: ast.AST, aliases: dict[str, str]) -> dict[str, str]:
    """Infer simple aliases to tarfile constructors, extraction methods, and data_filter."""
    inferred: dict[str, str] = {}
    current = dict(aliases)
    # A small bounded fixpoint handles chains such as ``open_tar = tarfile.open``
    # followed by ``open_again = open_tar`` without turning this into dataflow.
    for _ in range(4):
        changed = False
        for names, value in _assignment_pairs(scope):
            canonical = canonical_name(value, current)
            if canonical not in TARFILE_SAFE_CALLABLES:
                continue
            for name in names:
                # A proven instance binding is stronger than a callable alias.
                # Never let an earlier constructor-alias assignment downgrade it.
                if current.get(name) == "tarfile.TarFile":
                    continue
                if current.get(name) == canonical:
                    continue
                inferred[name] = canonical
                current[name] = canonical
                changed = True
        if not changed:
            break
    return inferred


def _tarfile_bindings(scope: ast.AST, aliases: dict[str, str]) -> dict[str, str]:
    """Infer names/attributes ever bound directly to a TarFile instance.

    Once a symbol is proven to hold a TarFile in the scope we conservatively keep
    treating extraction through that symbol as security-sensitive even if it is
    later reassigned. Dropping multiply-stored symbols created a fail-open bypass.
    """
    candidates: set[str] = set()

    for names, value in _assignment_pairs(scope):
        if isinstance(value, ast.Call) and canonical_name(value.func, aliases) in TARFILE_CONSTRUCTORS:
            candidates.update(names)

    for node in _scope_nodes(scope):
        if not isinstance(node, (ast.With, ast.AsyncWith)):
            continue
        for item in node.items:
            if (
                isinstance(item.context_expr, ast.Call)
                and canonical_name(item.context_expr.func, aliases) in TARFILE_CONSTRUCTORS
            ):
                candidates.update(_target_names(item.optional_vars))

    return {name: "tarfile.TarFile" for name in candidates}


def _scope_aliases(scope: ast.AST, import_map: dict[str, str]) -> dict[str, str]:
    aliases = dict(import_map)
    for _ in range(4):
        before = dict(aliases)
        aliases.update(_callable_aliases(scope, aliases))
        aliases.update(_tarfile_bindings(scope, aliases))
        # Instance bindings can make method aliases resolvable on the next pass.
        aliases.update(_callable_aliases(scope, aliases))
        if aliases == before:
            break
    return aliases


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
        aliases = _scope_aliases(scope, import_map)
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
    print("Archive extraction safety gate passed: all tracked tar extraction uses the data filter.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
