"""Extend the canonical Python SAST gate beyond ``backend/``.

The high-confidence scanner lives in ``backend/scripts/check_sast_security.py``.
Historically its Python file enumeration covered only ``backend/`` which left the
production ``skeleton/`` package and top-level repository tooling outside that
security boundary. Reuse the same violation engine here so the policy remains
single-sourced while coverage spans the rest of the Python runtime/tooling
surface.

Enumeration is deliberately implemented with explicit ``os.scandir`` traversal
rather than pathlib globbing. Security scanners must not interpret an unreadable,
raced, or symlinked source subtree as an empty/clean subtree.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
import os
from pathlib import Path
import runpy
import stat
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_SCANNER = REPO_ROOT / "backend" / "scripts" / "check_sast_security.py"
SCAN_ROOTS = (
    REPO_ROOT / "skeleton",
    REPO_ROOT / "scripts",
)
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".expo",
    "coverage",
}
SAFE_SCAN_ERRORS = {
    "required scan root missing",
    "required scan root must not be a symlink",
    "required scan root is not a directory",
    "required scan root metadata failure",
    "source traversal failure",
    "source traversal metadata failure",
    "source traversal encountered symlink",
}


def _validate_root(root: Path) -> None:
    """Validate one required scan root without following symlinks."""
    try:
        metadata = root.lstat()
    except FileNotFoundError:
        raise OSError("required scan root missing") from None
    except OSError:
        raise OSError("required scan root metadata failure") from None

    if stat.S_ISLNK(metadata.st_mode):
        raise OSError("required scan root must not be a symlink")
    if not stat.S_ISDIR(metadata.st_mode):
        raise OSError("required scan root is not a directory")


def _is_intentional_live_build(root: Path, path: Path) -> bool:
    """Keep ``skeleton/build`` in scope while skipping generated build trees."""
    return (
        root.name == "skeleton"
        and path.parent == root
        and path.name == "build"
    )


def _skip_directory(root: Path, path: Path) -> bool:
    return path.name in SKIP_DIRS and not _is_intentional_live_build(root, path)


def _walk_python_files(root: Path) -> Iterable[Path]:
    """Walk Python files deterministically and fail closed on traversal ambiguity."""
    _validate_root(root)
    stack = [root]

    while stack:
        current = stack.pop()
        try:
            entries = sorted(os.scandir(current), key=lambda entry: entry.name)
        except OSError:
            raise OSError("source traversal failure") from None

        child_dirs: list[Path] = []
        for entry in entries:
            path = Path(entry.path)
            if _skip_directory(root, path):
                continue

            try:
                metadata = entry.stat(follow_symlinks=False)
            except OSError:
                raise OSError("source traversal metadata failure") from None

            if stat.S_ISLNK(metadata.st_mode):
                raise OSError("source traversal encountered symlink")
            if stat.S_ISDIR(metadata.st_mode):
                child_dirs.append(path)
                continue
            if stat.S_ISREG(metadata.st_mode) and path.suffix.lower() == ".py":
                yield path

        stack.extend(reversed(child_dirs))


def python_files() -> Iterable[Path]:
    """Yield required core/tooling Python files with fail-closed enumeration."""
    for root in SCAN_ROOTS:
        yield from _walk_python_files(root)


def _root_label(root: Path) -> Path:
    try:
        return root.relative_to(REPO_ROOT)
    except ValueError:
        return root


def _load_violation_engine() -> Callable[[Path], list[str]]:
    if not BASE_SCANNER.is_file():
        raise RuntimeError("canonical SAST scanner missing")
    namespace: dict[str, Any] = runpy.run_path(str(BASE_SCANNER))
    engine = namespace.get("violations")
    if not callable(engine):
        raise RuntimeError("canonical SAST scanner does not expose violations(path)")
    return engine


def main() -> int:
    try:
        violations = _load_violation_engine()
    except Exception as exc:
        print(
            f"Repository Python SAST bootstrap failed: {type(exc).__name__}",
            file=sys.stderr,
        )
        return 2

    try:
        files = list(python_files())
    except OSError as exc:
        detail = str(exc)
        suffix = f": {detail}" if detail in SAFE_SCAN_ERRORS else ""
        print(
            f"Repository Python SAST scan failed: {type(exc).__name__}{suffix}",
            file=sys.stderr,
        )
        return 1

    findings: list[str] = []
    root_counts = {root: 0 for root in SCAN_ROOTS}
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
        print("High-confidence repository Python SAST violations detected:", file=sys.stderr)
        for finding in sorted(findings):
            print(f"  - {finding}", file=sys.stderr)
        return 1

    print(
        f"Repository Python SAST gate passed ({len(files)} core/tooling Python files; "
        + ", ".join(
            f"{_root_label(root)}={count}"
            for root, count in root_counts.items()
        )
        + ")."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
