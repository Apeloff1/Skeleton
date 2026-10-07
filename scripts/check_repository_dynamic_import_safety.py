#!/usr/bin/env python3
"""Fail CI on runtime-selected imports across core and repository tooling.

The canonical violation engine remains backend/scripts/check_dynamic_import_safety.py.
This wrapper applies that exact policy to skeleton/ and scripts/ without granting
new dynamic-import exceptions outside the backend allowlist.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_GATE_PATH = REPO_ROOT / "backend" / "scripts" / "check_dynamic_import_safety.py"
SCAN_ROOTS = (
    REPO_ROOT / "skeleton",
    REPO_ROOT / "scripts",
)


def _load_backend_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_backend_dynamic_import_safety",
        BACKEND_GATE_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load canonical dynamic-import scanner")
    module = importlib.util.module_from_spec(spec)
    # dataclasses and other import-time helpers resolve the defining module
    # through sys.modules. Mirror normal import semantics while executing the
    # canonical scanner, and fail closed without leaving a half-loaded module.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    return module


BACKEND_GATE = _load_backend_gate()


def _root_label(root: Path) -> Path:
    try:
        return root.relative_to(REPO_ROOT)
    except ValueError:
        return root


def python_files() -> Iterable[Path]:
    """Yield required core/tooling sources, failing closed on coverage loss."""
    seen: set[Path] = set()
    for root in SCAN_ROOTS:
        if root.is_symlink():
            raise BACKEND_GATE.DynamicImportScanError(
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


def main() -> int:
    findings: list[str] = []
    root_counts: dict[Path, int] = {root: 0 for root in SCAN_ROOTS}

    try:
        files = list(python_files())
    except BACKEND_GATE.DynamicImportScanError:
        print(
            "Repository dynamic-import safety scan failed: source traversal failure",
            file=sys.stderr,
        )
        return 1
    except OSError:
        print(
            "Repository dynamic-import safety scan failed: source traversal failure",
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
        findings.extend(violations(path))

    for root, count in root_counts.items():
        if count == 0:
            findings.append(
                f"scanner coverage failure: no Python files scanned under {_root_label(root)}"
            )

    if findings:
        print("Repository dynamic-import safety violations detected:", file=sys.stderr)
        for finding in sorted(set(findings)):
            print(f"  - {finding}", file=sys.stderr)
        return 1

    summary = ", ".join(
        f"{_root_label(root)}={count}" for root, count in root_counts.items()
    )
    print(
        f"Repository dynamic-import safety passed across {len(files)} Python files "
        f"({summary})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
