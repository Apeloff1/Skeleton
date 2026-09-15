#!/usr/bin/env python3
"""Fail CI on unsafe Python process execution anywhere in production/runtime roots.

This repository-wide gate composes the mature backend process scanner with an
additional argv check. It intentionally scans backend/, skeleton/, and scripts/
so host execution cannot move outside backend/ and silently escape policy.
"""

from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path
import stat
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


def display_path(path: Path) -> Path:
    try:
        return path.relative_to(REPO_ROOT)
    except ValueError:
        return path


def _validate_scan_root(root: Path) -> None:
    """Reject missing, symlinked, or non-directory runtime roots."""
    metadata = root.lstat()
    if stat.S_ISLNK(metadata.st_mode):
        raise OSError(f"scan root is a symlink: {display_path(root)}")
    if not stat.S_ISDIR(metadata.st_mode):
        raise OSError(f"scan root is not a directory: {display_path(root)}")


def iter_python_files(root: Path) -> Iterable[Path]:
    """Yield Python files using observable, non-symlink-following traversal."""
    _validate_scan_root(root)
    pending = [root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                if path.name in SKIP_DIRS:
                    continue
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    pending.append(path)
                    continue
                if entry.is_file(follow_symlinks=False) and path.suffix == ".py":
                    yield path


def python_files() -> Iterable[Path]:
    """Yield every Python file in required runtime/security roots exactly once."""
    seen: set[Path] = set()
    for root in SCAN_ROOTS:
        for path in iter_python_files(root):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            yield path


def _definitely_string_command(node: ast.AST) -> bool:
    """Return True only when the AST proves a subprocess command is string-like."""
    if isinstance(node, ast.Constant):
        return isinstance(node.value, (str, bytes))
    if isinstance(node, ast.JoinedStr):
        return True
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.Add):
            # If either operand is definitely string-like, successful + evaluation
            # yields a string/bytes command (otherwise Python raises before spawn).
            return _definitely_string_command(node.left) or _definitely_string_command(node.right)
        if isinstance(node.op, ast.Mod):
            # Percent-formatting a literal/f-string-like left operand yields text.
            return _definitely_string_command(node.left)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr in {"format", "join"}:
            return _definitely_string_command(node.func.value)
    return False


def _command_argument(node: ast.Call) -> ast.AST | None:
    if node.args:
        return node.args[0]
    for keyword in node.keywords:
        if keyword.arg == "args":
            return keyword.value
    return None


def _parse_tree(path: Path) -> tuple[ast.AST | None, list[str]]:
    label = display_path(path)
    try:
        source = path.read_text(encoding="utf-8")
        return ast.parse(source, filename=str(path)), []
    except (OSError, UnicodeError, SyntaxError) as exc:
        return None, [f"{label}: parse failure: {type(exc).__name__}"]


def _argv_violations_from_tree(path: Path, tree: ast.AST) -> list[str]:
    label = display_path(path)
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


def argv_violations(path: Path) -> list[str]:
    """Reject subprocess calls that are provably single-string commands."""
    tree, parse_findings = _parse_tree(path)
    if tree is None:
        return parse_findings
    return _argv_violations_from_tree(path, tree)


def violations(path: Path) -> list[str]:
    # Parse once before invoking the backend analyzer so malformed/unreadable
    # evidence is reported with a redacted exception class rather than raw text.
    tree, parse_findings = _parse_tree(path)
    if tree is None:
        return parse_findings
    return [*BACKEND_GATE.violations(path), *_argv_violations_from_tree(path, tree)]


def main() -> int:
    findings: list[str] = []
    scanned = 0
    try:
        for path in python_files():
            scanned += 1
            findings.extend(violations(path))
    except OSError as exc:
        findings.append(f"repository traversal failure: {type(exc).__name__}")

    if scanned == 0:
        findings.append("scanner coverage failure: no Python files were scanned")

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
