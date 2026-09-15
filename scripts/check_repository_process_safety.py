#!/usr/bin/env python3
"""Fail CI on unsafe Python process execution anywhere in production/runtime roots.

This repository-wide gate composes the mature backend process scanner with an
additional argv check.  It intentionally scans backend/, skeleton/, and scripts/
so host execution cannot move outside backend/ and silently escape policy.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_GATE_PATH = REPO_ROOT / "backend" / "scripts" / "check_process_safety.py"
SCAN_ROOTS = (
    REPO_ROOT / "backend",
    REPO_ROOT / "skeleton",
    REPO_ROOT / "scripts",
)
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", "legacy_root"}


def _load_backend_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_backend_process_safety", BACKEND_GATE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load backend process safety gate: {BACKEND_GATE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BACKEND_GATE = _load_backend_gate()
SUBPROCESS_CALLS = {f"subprocess.{name}" for name in BACKEND_GATE.SUBPROCESS_CALLS}


def python_files() -> Iterable[Path]:
    """Yield every Python file in the active runtime/security roots exactly once."""
    seen: set[Path] = set()
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            yield path


def display_path(path: Path) -> Path:
    try:
        return path.relative_to(REPO_ROOT)
    except ValueError:
        return path


def _definitely_string_command(node: ast.AST) -> bool:
    """Return True only when the AST proves a subprocess command is a string."""
    if isinstance(node, ast.Constant):
        return isinstance(node.value, (str, bytes))
    if isinstance(node, ast.JoinedStr):
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _definitely_string_command(node.left) and _definitely_string_command(node.right)
    return False


def _command_argument(node: ast.Call) -> ast.AST | None:
    if node.args:
        return node.args[0]
    for keyword in node.keywords:
        if keyword.arg == "args":
            return keyword.value
    return None


def argv_violations(path: Path) -> list[str]:
    """Reject subprocess calls that are provably single-string commands.

    Dynamic values are left to the existing policy scanner and normal type/tests;
    this check is deliberately high-confidence so it does not reject variables
    that hold validated argument vectors.
    """
    label = display_path(path)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        return [f"{label}: parse failure: {exc}"]

    aliases = BACKEND_GATE.assignment_aliases(tree, BACKEND_GATE.import_aliases(tree))
    findings: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = BACKEND_GATE.canonical_name(node.func, aliases)
        if name not in SUBPROCESS_CALLS:
            continue
        command = _command_argument(node)
        if command is not None and _definitely_string_command(command):
            findings.append(
                f"{label}:{node.lineno}: {name} command must be an argument vector, not a string"
            )
    return findings


def violations(path: Path) -> list[str]:
    return [*BACKEND_GATE.violations(path), *argv_violations(path)]


def main() -> int:
    findings: list[str] = []
    scanned = 0
    for path in python_files():
        scanned += 1
        findings.extend(violations(path))

    if findings:
        print("Repository process-safety violations detected:", file=sys.stderr)
        for finding in sorted(set(findings)):
            print(f"  - {finding}", file=sys.stderr)
        return 1

    print(
        f"Repository process safety passed across {scanned} Python files: "
        "no shell execution, opaque process lookup, or definite string subprocess commands found."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
