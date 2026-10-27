#!/usr/bin/env python3
"""Fail CI on unsafe deserialization across core and repository tooling.

The canonical violation engine remains backend/scripts/check_deserialization_safety.py.
This wrapper extends that exact policy to skeleton/ and scripts/ while keeping
coverage fail-closed for missing, unreadable, symlinked, or empty required roots.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import importlib.util
import os
from pathlib import Path
import sys
from types import ModuleType
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_GATE_PATH = REPO_ROOT / "backend" / "scripts" / "check_deserialization_safety.py"
SCAN_ROOTS = (
    REPO_ROOT / "skeleton",
    REPO_ROOT / "scripts",
)
# Bound worker count and transfer batches: all files still receive the same
# canonical AST policy, and any failed worker fails the entire gate closed.
PARALLEL_MIN_FILES = 1024
BATCH_SIZE = 128
MAX_WORKERS = 2


def _load_backend_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_backend_deserialization_safety",
        BACKEND_GATE_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load canonical deserialization scanner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BACKEND_GATE = _load_backend_gate()


def _root_label(root: Path) -> Path:
    try:
        return root.relative_to(REPO_ROOT)
    except ValueError:
        return root


def python_files() -> Iterable[Path]:
    """Yield every required core/tooling Python source exactly once."""
    seen: set[Path] = set()
    for root in SCAN_ROOTS:
        if root.is_symlink():
            raise BACKEND_GATE.DeserializationScanError(
                "required scan root must not be a symlink"
            )
        for path in BACKEND_GATE.python_files(root):
            absolute = path.absolute()
            if absolute in seen:
                continue
            seen.add(absolute)
            yield path


def violations(path: Path) -> list[str]:
    return BACKEND_GATE.violations(path)


def _scan_batch(paths: list[Path]) -> list[str]:
    """Run the canonical policy on every member of one deterministic batch."""
    findings: list[str] = []
    for path in paths:
        findings.extend(violations(path))
    return findings


def _scan_files(paths: list[Path]) -> list[str]:
    """Bound memory and process overhead while preserving complete coverage.

    Imported validator modules and small fixture suites remain single-process
    so callers can inject isolated test roots without pickle/import surprises.
    The production CLI parallelizes large scans only; map() propagates worker
    exceptions, and its results are consumed in input order.
    """
    workers = min(MAX_WORKERS, os.cpu_count() or 1)
    if __name__ != "__main__" or len(paths) < PARALLEL_MIN_FILES or workers < 2:
        return _scan_batch(paths)
    batches = (
        paths[start : start + BATCH_SIZE]
        for start in range(0, len(paths), BATCH_SIZE)
    )
    findings: list[str] = []
    with ProcessPoolExecutor(max_workers=workers) as executor:
        for batch_findings in executor.map(_scan_batch, batches):
            findings.extend(batch_findings)
    return findings


def main() -> int:
    findings: list[str] = []
    root_counts: dict[Path, int] = {root: 0 for root in SCAN_ROOTS}

    try:
        files = list(python_files())
    except BACKEND_GATE.DeserializationScanError:
        print(
            "Repository deserialization safety scan failed: source traversal failure",
            file=sys.stderr,
        )
        return 1
    except OSError:
        print(
            "Repository deserialization safety scan failed: source traversal failure",
            file=sys.stderr,
        )
        return 1

    for path in files:
        for root in SCAN_ROOTS:
            try:
                path.relative_to(root)
            except ValueError:
                continue
            root_counts[root] += 1
            break
    try:
        findings.extend(_scan_files(files))
    except Exception as exc:
        print(
            f"Repository deserialization safety scan failed: "
            f"source inspection failure ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 1

    for root, count in root_counts.items():
        if count == 0:
            findings.append(
                f"scanner coverage failure: no Python files scanned under {_root_label(root)}"
            )

    if findings:
        print("Unsafe repository deserialization patterns detected:", file=sys.stderr)
        for finding in sorted(set(findings)):
            print(f"  - {finding}", file=sys.stderr)
        return 1

    summary = ", ".join(
        f"{_root_label(root)}={count}" for root, count in root_counts.items()
    )
    print(
        f"Repository deserialization safety passed across {len(files)} Python files "
        f"({summary}): no unsafe object loaders found."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
