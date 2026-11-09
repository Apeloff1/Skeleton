"""Fail closed when repository security scanners cannot enumerate their scan surface.

Pathlib glob/rglob traversal can hide directory-enumeration failures on supported
Python versions. Secret, SAST, and malware scanners perform their own per-file
checks, but they must not treat an unreadable subtree as an empty/clean subtree.
This preflight uses an explicit os.walk error channel before those scanners run.
"""
from __future__ import annotations

import os
from pathlib import Path
import stat
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "coverage",
    ".next",
    ".expo",
    "__pycache__",
}


class ScanSurfaceTraversalError(RuntimeError):
    """Raised when os.walk reports an unreadable repository subtree."""


def _display_path(path: Path, root: Path) -> Path:
    try:
        return path.relative_to(root)
    except ValueError:
        return path


def _walk_error(exc: OSError) -> None:
    """Turn os.walk's callback-only failure channel into fail-closed control flow."""
    raise ScanSurfaceTraversalError(
        f"repository traversal failure: {type(exc).__name__}"
    ) from None


def audit_scan_surface(root: Path = REPO_ROOT) -> tuple[list[str], int]:
    """Return sanitized findings and the count of regular files proved enumerable."""
    findings: list[str] = []
    regular_files = 0

    try:
        root_metadata = root.lstat()
    except OSError as exc:
        return [f"scanner root metadata failure: {type(exc).__name__}"], 0
    if not stat.S_ISDIR(root_metadata.st_mode):
        return ["scanner coverage failure: repository root is not a directory"], 0

    try:
        for current, dirnames, filenames in os.walk(
            root,
            topdown=True,
            onerror=_walk_error,
            followlinks=False,
        ):
            current_path = Path(current)
            descend: list[str] = []

            for name in dirnames:
                if name in SKIP_DIRS:
                    continue
                path = current_path / name
                try:
                    metadata = path.lstat()
                except OSError as exc:
                    findings.append(
                        f"{_display_path(path, root)}: scanner metadata failure: "
                        f"{type(exc).__name__}"
                    )
                    continue
                if stat.S_ISLNK(metadata.st_mode):
                    continue
                if not stat.S_ISDIR(metadata.st_mode):
                    findings.append(
                        f"{_display_path(path, root)}: scanner directory type changed"
                    )
                    continue
                descend.append(name)

            # Prune skipped, symlinked, unreadable, or type-raced directories before
            # os.walk descends into them. Any unreadable real directory is already a
            # blocking finding above.
            dirnames[:] = descend

            for name in filenames:
                path = current_path / name
                try:
                    metadata = path.lstat()
                except OSError as exc:
                    findings.append(
                        f"{_display_path(path, root)}: scanner metadata failure: "
                        f"{type(exc).__name__}"
                    )
                    continue
                if stat.S_ISLNK(metadata.st_mode):
                    continue
                if stat.S_ISREG(metadata.st_mode):
                    regular_files += 1
                    continue
                findings.append(
                    f"{_display_path(path, root)}: unsupported repository file type"
                )
    except ScanSurfaceTraversalError as exc:
        findings.append(str(exc))
    except OSError as exc:
        # Defensive fallback for platform-specific traversal failures that bypass
        # os.walk's onerror callback. Never echo raw OS exception text into CI.
        findings.append(f"repository traversal failure: {type(exc).__name__}")

    if regular_files == 0:
        findings.append("scanner coverage failure: no regular repository files were enumerated")
    return findings, regular_files


def main() -> int:
    findings, regular_files = audit_scan_surface()
    if findings:
        print("Security scanner surface preflight failed:", file=sys.stderr)
        for finding in sorted(set(findings)):
            print(f"  - {finding}", file=sys.stderr)
        return 1

    print(
        f"Security scanner surface preflight passed across {regular_files} regular files."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
