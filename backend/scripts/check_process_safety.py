"""Fail CI on unsafe process invocation patterns in backend Python code.

This guard is intentionally dependency-free so it can run before application
imports or third-party package installation.  It prevents two high-risk process
execution patterns from entering the backend:

* ``subprocess`` calls with ``shell=True``
* ``os.system(...)``

Argument-vector subprocess execution remains permitted and is reviewed through
the normal execution-boundary tests.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules"}


def python_files() -> Iterable[Path]:
    for path in ROOT.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


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


def literal_true(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def violations(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        return [f"{path.relative_to(ROOT)}: parse failure: {exc}"]

    findings: list[str] = []
    relative = path.relative_to(ROOT)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        name = dotted_name(node.func)
        if name == "os.system":
            findings.append(f"{relative}:{node.lineno}: os.system() is forbidden")
            continue

        if name in {
            "subprocess.run",
            "subprocess.call",
            "subprocess.check_call",
            "subprocess.check_output",
            "subprocess.Popen",
        }:
            for keyword in node.keywords:
                if keyword.arg == "shell" and literal_true(keyword.value):
                    findings.append(
                        f"{relative}:{node.lineno}: {name}(..., shell=True) is forbidden"
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

    print("Process safety gate passed: no shell=True or os.system() calls found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
