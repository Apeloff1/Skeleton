#!/usr/bin/env python3
"""Classify tracked repository paths for consolidation inventory.

Every repository-relative path must resolve to exactly one closed class:

* archive — frozen snapshots and retired trees (not live production)
* vendor — third-party dependency trees
* generated — caches, linguist-generated data, and compressed dumps
* fixture — synthetic test data
* binary — non-text assets and tracked engine binaries
* canonical — live first-party production trees
* first-party — owner-controlled source that is not a canonical production tree

Unknown paths fail closed. Classification is exclusive and ordered: a more
specific class always wins (archive before canonical, generated before binary,
fixture before first-party tests).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections import Counter
from pathlib import Path, PurePosixPath


REPO_ROOT = Path(__file__).resolve().parents[1]

CLASSES = (
    "archive",
    "vendor",
    "generated",
    "fixture",
    "binary",
    "canonical",
    "first-party",
)
CLASS_SET = frozenset(CLASSES)

ARCHIVE_PREFIXES = (
    "satellites/branch-snapshots/",
    "docs/archive/",
    "tests/legacy_root/",
    "scripts/legacy_root/",
)

VENDOR_PARTS = frozenset({"node_modules", "vendor", "third_party", "third-party"})

GENERATED_PREFIXES = (
    "memory/mongo_backup/",
    "backend/data/",
)
GENERATED_PARTS = frozenset(
    {
        "__pycache__",
        "dist",
        "build",
        "coverage",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".next",
        ".expo",
        "htmlcov",
        "web-build",
        ".tox",
        ".nox",
    }
)
GENERATED_SUFFIXES = frozenset({".pyc", ".pyo", ".egg", ".zst", ".snapshot"})
GENERATED_FILENAMES = frozenset({"test_result.md"})

FIXTURE_PREFIXES = ("skeleton/testing/data/",)
FIXTURE_PARTS = frozenset({"fixtures", "testdata", "test_data"})

# Test support lives beside production trees but is not a canonical owner.
FIRST_PARTY_TEST_PREFIXES = (
    "skeleton/testing/",
    "backend/tests/",
)

CANONICAL_PREFIXES = (
    "skeleton/",
    "backend/",
    "frontend/",
)

# Transitional/support roots remain first-party but cannot silently acquire
# canonical runtime ownership. machine/architecture.json is authoritative.
FIRST_PARTY_PREFIXES = (
    "core/",
    "eval/",
    "java-accelerators/",
    "scripts/",
    "tests/",
    "docs/",
    ".github/",
    ".cursor/",
    "memory/",
    "satellites/",
    ".emergent/",
    ".machine/",
    "machine/",
    "packaging/",
)

BINARY_SUFFIXES = frozenset(
    {
        ".zip",
        ".apk",
        ".aab",
        ".ipa",
        ".bson",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".gif",
        ".mp4",
        ".mp3",
        ".ttf",
        ".pdf",
        ".wasm",
        ".so",
        ".dll",
        ".exe",
        ".bin",
        ".whl",
    }
)
BINARY_FILENAMES = frozenset({"godot"})


def normalize_repo_path(path: object) -> str:
    """Return a POSIX repository-relative path, or raise ValueError."""
    if not isinstance(path, str) or not path or "\x00" in path:
        raise ValueError("path must be a non-empty repository-relative POSIX string")
    if "\\" in path:
        raise ValueError("path must use POSIX separators")
    pure = PurePosixPath(path)
    canonical = pure.as_posix()
    if (
        pure.is_absolute()
        or any(part in {"", ".", ".."} for part in pure.parts)
        or canonical != path
    ):
        raise ValueError("path must be repository-relative and normalized")
    return canonical


def _has_prefix(path: str, prefixes: tuple[str, ...]) -> bool:
    return any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in prefixes)


def _parts(path: str) -> tuple[str, ...]:
    return PurePosixPath(path).parts


def _filename(path: str) -> str:
    return PurePosixPath(path).name


def _suffix(path: str) -> str:
    return PurePosixPath(path).suffix.lower()


def _is_fixture_name(name: str) -> bool:
    lowered = name.lower()
    return lowered.startswith("fixture_") or "_fixture." in lowered


def classify_path(path: object) -> str:
    """Return the closed inventory class for ``path``.

    Invalid or unrecognized paths return ``unknown`` so callers can fail closed
    without treating a classification miss as canonical source.
    """
    try:
        normalized = normalize_repo_path(path)
    except ValueError:
        return "unknown"

    parts = _parts(normalized)
    name = _filename(normalized)
    suffix = _suffix(normalized)

    if _has_prefix(normalized, ARCHIVE_PREFIXES):
        return "archive"
    if any(part in VENDOR_PARTS for part in parts):
        return "vendor"
    if (
        _has_prefix(normalized, GENERATED_PREFIXES)
        or any(
            (
                part in GENERATED_PARTS
                and not (part == "build" and normalized.startswith("skeleton/build/"))
            )
            or part.endswith(".egg-info")
            for part in parts
        )
        or suffix in GENERATED_SUFFIXES
        or name in GENERATED_FILENAMES
    ):
        return "generated"
    if (
        _has_prefix(normalized, FIXTURE_PREFIXES)
        or any(part in FIXTURE_PARTS for part in parts)
        or _is_fixture_name(name)
    ):
        return "fixture"
    if suffix in BINARY_SUFFIXES or name in BINARY_FILENAMES:
        return "binary"
    if _has_prefix(normalized, FIRST_PARTY_TEST_PREFIXES):
        return "first-party"
    if _has_prefix(normalized, CANONICAL_PREFIXES):
        return "canonical"
    if _has_prefix(normalized, FIRST_PARTY_PREFIXES) or "/" not in normalized:
        return "first-party"
    return "unknown"


def validate_source_path_inventory(paths: object) -> list[str]:
    """Fail closed unless every path classifies to exactly one known class."""
    if not isinstance(paths, (list, tuple)):
        return ["source path inventory must be a list of repository-relative paths"]

    errors: list[str] = []
    seen: set[str] = set()
    for index, path in enumerate(paths):
        label = f"paths[{index}]"
        if not isinstance(path, str):
            errors.append(f"{label} must be a string")
            continue
        try:
            normalized = normalize_repo_path(path)
        except ValueError as exc:
            errors.append(f"{label}: {exc}")
            continue
        if normalized in seen:
            errors.append(f"duplicate source path: {normalized}")
            continue
        seen.add(normalized)

        klass = classify_path(normalized)
        if klass not in CLASS_SET:
            errors.append(f"{normalized}: unclassified source path")
        elif klass not in CLASSES:
            errors.append(f"{normalized}: class {klass!r} is outside the closed class order")

    return errors


def tracked_source_paths(repo_root: Path = REPO_ROOT) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repo_root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return [
        entry.decode("utf-8", errors="surrogateescape")
        for entry in result.stdout.split(b"\0")
        if entry
    ]


def summarize(paths: list[str]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for path in paths:
        counts[classify_path(path)] += 1
    return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path",
        action="append",
        dest="paths",
        default=None,
        help="Classify a specific repository-relative path (repeatable). Default: all tracked files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = args.paths if args.paths is not None else tracked_source_paths()
    errors = validate_source_path_inventory(paths)
    if errors:
        print("source-path-inventory: rejected", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    counts = summarize(paths)
    rendered = ", ".join(f"{klass}={counts[klass]}" for klass in CLASSES)
    extra = sorted(klass for klass in counts if klass not in CLASS_SET)
    if extra:
        print("source-path-inventory: rejected", file=sys.stderr)
        print(f"  - unexpected classes: {', '.join(extra)}", file=sys.stderr)
        return 1

    print(f"source-path-inventory: OK ({len(paths)} tracked paths; {rendered})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
