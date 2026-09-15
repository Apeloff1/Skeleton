"""Fail-closed runner for the backend process-safety analyzer.

The analyzer in ``check_process_safety.py`` owns AST policy semantics. This
runner owns repository discovery and evidence-integrity guarantees so directory
enumeration, parse/read failures, or empty coverage cannot be mistaken for a
clean scan.
"""
from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path
import sys
from types import ModuleType
from typing import Iterable

ANALYZER_PATH = Path(__file__).with_name("check_process_safety.py")


def _load_analyzer() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_process_safety_analyzer", ANALYZER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load process safety analyzer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ANALYZER = _load_analyzer()
ROOT = ANALYZER.ROOT
SKIP_DIRS = set(ANALYZER.SKIP_DIRS)


def display_path(path: Path) -> Path:
    try:
        return path.relative_to(ROOT)
    except ValueError:
        return path


def python_files() -> Iterable[Path]:
    """Yield Python source while surfacing every directory-enumeration failure."""
    pending = [ROOT]
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


def violations(path: Path) -> list[str]:
    """Preflight source evidence before invoking the mature policy analyzer."""
    label = display_path(path)
    try:
        source = path.read_text(encoding="utf-8")
        ast.parse(source, filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        return [f"{label}: parse failure: {type(exc).__name__}"]
    return ANALYZER.violations(path)


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
        print("Unsafe process invocation patterns detected:", file=sys.stderr)
        for finding in sorted(set(findings)):
            print(f"  - {finding}", file=sys.stderr)
        return 1

    print(
        f"Process safety gate passed across {scanned} Python files: no unsafe shell execution, "
        "statically obvious string-shaped subprocess commands, opaque subprocess kwargs, "
        "dynamic process lookup, process-sensitive star imports, unsafe process partials, "
        "unsafe process namespace access, os.system(), or os.popen() calls found."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
