"""Fail CI on unsafe process invocation patterns in backend Python code.

Dependency-free by design so it can run before application imports. The scanner
tracks common import, assignment, getattr, and namespace-mapping aliases to
prevent trivial process policy bypasses.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules"}
SUBPROCESS_CALLS = {"run", "call", "check_call", "check_output", "Popen"}
TRACKED_MODULES = {"asyncio", "os", "subprocess"}
UNSAFE_CALLS = {
    "os.system": "os.system() is forbidden",
    "os.popen": "os.popen() is forbidden",
    "asyncio.create_subprocess_shell": "asyncio.create_subprocess_shell() is forbidden",
}


def python_files() -> Iterable[Path]:
    for path in ROOT.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def display_path(path: Path) -> Path:
    try:
        return path.relative_to(ROOT)
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


def literal_false(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is False


def literal_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def star_import_violations(tree: ast.AST, label: Path) -> list[str]:
    findings: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module not in TRACKED_MODULES:
            continue
        if any(item.name == "*" for item in node.names):
            findings.append(
                f"{label}:{node.lineno}: star import from {node.module} is forbidden because process call provenance cannot be statically proven"
            )
    return findings


def import_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                if item.name in TRACKED_MODULES:
                    aliases[item.asname or item.name] = item.name
        elif isinstance(node, ast.ImportFrom) and node.module in TRACKED_MODULES:
            for item in node.names:
                if item.name != "*":
                    aliases[item.asname or item.name] = f"{node.module}.{item.name}"
    return aliases


def namespace_mapping_owner(node: ast.AST, aliases: dict[str, str]) -> str | None:
    if isinstance(node, ast.Attribute) and node.attr == "__dict__":
        owner = canonical_name(node.value, aliases)
        return owner if owner in TRACKED_MODULES else None

    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "vars"
        and len(node.args) == 1
        and not node.keywords
    ):
        owner = canonical_name(node.args[0], aliases)
        return owner if owner in TRACKED_MODULES else None

    return None


def canonical_name(node: ast.AST, aliases: dict[str, str]) -> str | None:
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        and len(node.args) >= 2
    ):
        owner = canonical_name(node.args[0], aliases)
        attribute = literal_string(node.args[1])
        if owner in TRACKED_MODULES and attribute is not None:
            return f"{owner}.{attribute}"
        return None

    if isinstance(node, ast.Subscript):
        owner = namespace_mapping_owner(node.value, aliases)
        attribute = literal_string(node.slice)
        if owner in TRACKED_MODULES and attribute is not None:
            return f"{owner}.{attribute}"
        return None

    name = dotted_name(node)
    if not name:
        return None
    root, dot, suffix = name.partition(".")
    replacement = aliases.get(root)
    if replacement is None:
        return name
    return replacement + (f".{suffix}" if dot else "")


def assignment_aliases(tree: ast.AST, aliases: dict[str, str]) -> dict[str, str]:
    """Resolve simple aliases assigned from tracked process callables."""

    resolved = dict(aliases)
    assignments: list[tuple[str, ast.AST]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assignments.append((target.id, node.value))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value:
            assignments.append((node.target.id, node.value))

    tracked_names = UNSAFE_CALLS.keys() | {f"subprocess.{call}" for call in SUBPROCESS_CALLS}
    changed = True
    while changed:
        changed = False
        for target, value in assignments:
            source = canonical_name(value, resolved)
            if source in tracked_names and resolved.get(target) != source:
                resolved[target] = source
                changed = True

    return resolved


def dynamic_getattr_violation(node: ast.Call, aliases: dict[str, str]) -> str | None:
    if not (isinstance(node.func, ast.Name) and node.func.id == "getattr" and len(node.args) >= 2):
        return None
    owner = canonical_name(node.args[0], aliases)
    attribute = node.args[1]
    if owner not in TRACKED_MODULES:
        return None
    if literal_string(attribute) is not None:
        return None
    return f"dynamic getattr() on {owner} is forbidden because process policy cannot be statically proven"


def dynamic_namespace_mapping_violation(node: ast.Subscript, aliases: dict[str, str]) -> str | None:
    owner = namespace_mapping_owner(node.value, aliases)
    if owner not in TRACKED_MODULES:
        return None
    if literal_string(node.slice) is not None:
        return None
    return f"dynamic namespace lookup on {owner} is forbidden because process policy cannot be statically proven"


def violations(path: Path) -> list[str]:
    label = display_path(path)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        return [f"{label}: parse failure: {exc}"]

    aliases = assignment_aliases(tree, import_aliases(tree))
    findings = star_import_violations(tree, label)

    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript):
            dynamic_mapping_violation = dynamic_namespace_mapping_violation(node, aliases)
            if dynamic_mapping_violation:
                findings.append(f"{label}:{node.lineno}: {dynamic_mapping_violation}")

        if not isinstance(node, ast.Call):
            continue

        dynamic_violation = dynamic_getattr_violation(node, aliases)
        if dynamic_violation:
            findings.append(f"{label}:{node.lineno}: {dynamic_violation}")
            continue

        name = canonical_name(node.func, aliases)
        if name in UNSAFE_CALLS:
            findings.append(f"{label}:{node.lineno}: {UNSAFE_CALLS[name]}")
            continue

        if name in {f"subprocess.{call}" for call in SUBPROCESS_CALLS}:
            for keyword in node.keywords:
                if keyword.arg is None:
                    findings.append(
                        f"{label}:{node.lineno}: {name}(..., **kwargs) is forbidden because shell policy cannot be statically proven"
                    )
                    continue
                if keyword.arg == "shell" and not literal_false(keyword.value):
                    findings.append(
                        f"{label}:{node.lineno}: {name}(..., shell=...) is forbidden unless shell=False is literal"
                    )

    return findings


def main() -> int:
    findings: list[str] = []
    for path in python_files():
        findings.extend(violations(path))

    if findings:
        print("Unsafe process invocation patterns detected:", file=sys.stderr)
        for finding in sorted(findings):
            print(f"  - {finding}", file=sys.stderr)
        return 1

    print(
        "Process safety gate passed: no unsafe shell execution, opaque subprocess kwargs, "
        "dynamic process lookup, process-sensitive star imports, os.system(), or os.popen() calls found."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
