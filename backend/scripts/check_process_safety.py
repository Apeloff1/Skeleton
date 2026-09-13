"""Fail CI on unsafe process invocation patterns in backend Python code.

Dependency-free by design so it can run before application imports. The scanner
tracks common import aliases to prevent trivial bypasses such as ``import
subprocess as sp`` or ``from subprocess import run``.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules"}
SUBPROCESS_CALLS = {"run", "call", "check_call", "check_output", "Popen"}
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


def import_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    tracked_modules = {"asyncio", "os", "subprocess"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                if item.name in tracked_modules:
                    aliases[item.asname or item.name] = item.name
        elif isinstance(node, ast.ImportFrom) and node.module in tracked_modules:
            for item in node.names:
                aliases[item.asname or item.name] = f"{node.module}.{item.name}"
    return aliases


def canonical_name(node: ast.AST, aliases: dict[str, str]) -> str | None:
    name = dotted_name(node)
    if not name:
        return None
    root, dot, suffix = name.partition(".")
    replacement = aliases.get(root)
    if replacement is None:
        return name
    return replacement + (f".{suffix}" if dot else "")


def violations(path: Path) -> list[str]:
    label = display_path(path)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        return [f"{label}: parse failure: {exc}"]

    aliases = import_aliases(tree)
    findings: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
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
        "Process safety gate passed: no shell execution, opaque subprocess kwargs, os.system(), or os.popen() calls found."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
