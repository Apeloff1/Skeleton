"""Extend the canonical Python SAST gate beyond ``backend/``.

The high-confidence scanner lives in ``backend/scripts/check_sast_security.py``.
Historically its Python file enumeration covered only ``backend/`` which left the
production ``skeleton/`` package and top-level repository tooling outside that
security boundary. Reuse the same violation engine here so the policy remains
single-sourced while coverage spans the rest of the Python runtime/tooling
surface.
"""
from __future__ import annotations

from pathlib import Path
import runpy
import sys
from collections.abc import Callable, Iterable
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


def _relative_scan_parts(path: Path, root: Path) -> tuple[str, ...]:
    """Return stable scan-relative parts without assuming roots live in REPO_ROOT.

    Tests intentionally replace ``SCAN_ROOTS`` with temporary directories.  The
    security scanner must preserve that dependency-injection seam rather than
    crashing while formatting repository-relative paths.  Prefix the relative
    path with the configured root's logical name so the existing ``skeleton/build``
    exception remains precise and no arbitrary parent directories affect policy.
    """
    return (root.name, *path.relative_to(root).parts)


def python_files() -> Iterable[Path]:
    """Yield required core/tooling Python files, failing closed on missing roots."""
    for root in SCAN_ROOTS:
        if not root.exists():
            raise OSError("required scan root missing")
        if root.is_symlink():
            raise OSError("required scan root must not be a symlink")
        for path in root.rglob("*.py"):
            parts = _relative_scan_parts(path, root)
            filtered_parts = (
                (parts[0], *parts[2:])
                if len(parts) >= 2 and parts[:2] == ("skeleton", "build")
                else parts
            )
            if any(part in SKIP_DIRS for part in filtered_parts):
                continue
            yield path


def _root_label(root: Path) -> Path:
    try:
        return root.relative_to(REPO_ROOT)
    except ValueError:
        return root


def _load_violation_engine() -> Callable[[Path], list[str]]:
    if not BASE_SCANNER.is_file():
        raise RuntimeError(f"canonical SAST scanner missing: {BASE_SCANNER}")
    namespace: dict[str, Any] = runpy.run_path(str(BASE_SCANNER))
    engine = namespace.get("violations")
    if not callable(engine):
        raise RuntimeError("canonical SAST scanner does not expose violations(path)")
    return engine


def main() -> int:
    try:
        violations = _load_violation_engine()
    except Exception as exc:
        print(f"Repository Python SAST bootstrap failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    try:
        files = list(python_files())
    except (OSError, ValueError) as exc:
        detail = str(exc)
        safe_details = {
            "required scan root missing",
            "required scan root must not be a symlink",
        }
        suffix = f": {detail}" if detail in safe_details else ""
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
