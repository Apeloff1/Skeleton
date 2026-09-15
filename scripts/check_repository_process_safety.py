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


class ScanCoverageError(RuntimeError):
    """Raised when the scanner cannot prove its complete intended file surface."""


def _load_backend_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_backend_process_safety", BACKEND_GATE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load backend process safety gate: {BACKEND_GATE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BACKEND_GATE = _load_backend_gate()
SUBPROCESS_CALLS = {f"subprocess.{name}" for name in BACKEND_GATE.SUBPROCESS_CALLS}


def _scan_label(path: Path) -> str:
    """Return a repository-relative diagnostic label without leaking outside paths."""
    try:
        return path.relative_to(REPO_ROOT).as_posix() or "."
    except ValueError:
        return "<outside-repository>"


def _walk_error(error: OSError) -> None:
    location = Path(error.filename) if error.filename else REPO_ROOT
    raise ScanCoverageError(
        f"{_scan_label(location)}: repository traversal failure: {type(error).__name__}"
    ) from None


def _metadata(path: Path, *, kind: str) -> os.stat_result:
    try:
        return path.lstat()
    except OSError as exc:
        raise ScanCoverageError(
            f"{_scan_label(path)}: {kind} metadata failure: {type(exc).__name__}"
        ) from None


def python_files() -> Iterable[Path]:
    """Yield every regular Python file in every required scan root, or fail closed."""
    seen: set[Path] = set()
    files: list[Path] = []

    for root in SCAN_ROOTS:
        root_meta = _metadata(root, kind="scan root")
        if stat.S_ISLNK(root_meta.st_mode):
            raise ScanCoverageError(f"{_scan_label(root)}: scan root must not be a symlink")
        if not stat.S_ISDIR(root_meta.st_mode):
            raise ScanCoverageError(f"{_scan_label(root)}: scan root is not a directory")

        root_count = 0
        try:
            for current, dirnames, filenames in os.walk(
                root,
                topdown=True,
                onerror=_walk_error,
                followlinks=False,
            ):
                current_path = Path(current)
                descend: list[str] = []
                for name in sorted(dirnames):
                    if name in SKIP_DIRS or name.endswith(".egg-info"):
                        continue
                    path = current_path / name
                    metadata = _metadata(path, kind="scan directory")
                    if stat.S_ISLNK(metadata.st_mode):
                        continue
                    if not stat.S_ISDIR(metadata.st_mode):
                        raise ScanCoverageError(
                            f"{_scan_label(path)}: scan directory type changed"
                        )
                    descend.append(name)
                dirnames[:] = descend

                for filename in sorted(filenames):
                    if not filename.endswith(".py"):
                        continue
                    path = current_path / filename
                    metadata = _metadata(path, kind="scan file")
                    if stat.S_ISLNK(metadata.st_mode):
                        continue
                    if not stat.S_ISREG(metadata.st_mode):
                        raise ScanCoverageError(
                            f"{_scan_label(path)}: unsupported Python scan file type"
                        )
                    identity = path.absolute()
                    if identity in seen:
                        continue
                    seen.add(identity)
                    files.append(path)
                    root_count += 1
        except ScanCoverageError:
            raise
        except OSError as exc:
            raise ScanCoverageError(
                f"{_scan_label(root)}: repository traversal failure: {type(exc).__name__}"
            ) from None

        if root_count == 0:
            raise ScanCoverageError(
                f"{_scan_label(root)}: scanner coverage failure: no regular Python files were enumerated"
            )

    yield from files


def display_path(path: Path) -> Path:
    try:
        return path.relative_to(REPO_ROOT)
    except ValueError:
        return path


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
    try:
        paths = list(python_files())
    except ScanCoverageError as exc:
        print("Repository process-safety scan incomplete:", file=sys.stderr)
        print(f"  - {exc}", file=sys.stderr)
        return 2

    for path in paths:
        findings.extend(violations(path))

    if findings:
        print("Repository process-safety violations detected:", file=sys.stderr)
        for finding in sorted(set(findings)):
            print(f"  - {finding}", file=sys.stderr)
        return 1

    print(
        f"Repository process safety passed across {len(paths)} Python files: "
        "no shell execution, opaque process lookup, or definite string subprocess commands found."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
