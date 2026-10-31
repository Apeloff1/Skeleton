#!/usr/bin/env python3
"""Partition the entire canonical domain pytest file inventory without omission.

Each CI shard receives an independent checkout. The only excluded test module is
the existing separately executed advisory engine-handoff recovery suite.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = "test_engine_handoff_recovery.py"


def discover(root: Path) -> tuple[Path, ...]:
    """Fail closed on missing suites, symlinks, or untrusted file paths."""
    if not root.is_dir() or root.is_symlink():
        raise ValueError("canonical domain suite directory is absent or linked")
    root_real = root.resolve()
    found = set(root.rglob("test_*.py")) | set(root.rglob("*_test.py"))
    result = []
    for path in sorted(found):
        if path.name == EXCLUDED and path.parent == root:
            continue
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root_real):
            raise ValueError(f"unsafe canonical domain test path: {path}")
        if any(parent.is_symlink() for parent in path.parents if parent != root and root in parent.parents):
            raise ValueError(f"linked canonical domain test directory: {path}")
        result.append(path)
    if not result:
        raise ValueError("canonical domain test collection is empty")
    return tuple(result)


def partition(root: Path, count: int) -> tuple[tuple[Path, ...], ...]:
    """Greedy size-balanced, deterministic, exhaustive and disjoint file partitions."""
    if count < 1:
        raise ValueError("shard count must be positive")
    files = discover(root)
    if count > len(files):
        raise ValueError("more shards than canonical test modules")
    groups: list[list[Path]] = [[] for _ in range(count)]
    weights = [0] * count
    for path in sorted(files, key=lambda p: (-p.stat().st_size, p.as_posix())):
        index = min(range(count), key=lambda i: (weights[i], i))
        groups[index].append(path)
        weights[index] += path.stat().st_size
    shards = tuple(tuple(sorted(group)) for group in groups)
    if any(not group for group in shards):
        raise ValueError("empty canonical test shard")
    if set(path for group in shards for path in group) != set(files) or sum(map(len, shards)) != len(files):
        raise ValueError("canonical test inventory coverage mismatch")
    return shards


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=int, required=True)
    parser.add_argument("--count", type=int, required=True)
    args = parser.parse_args()
    try:
        shards = partition(ROOT / "skeleton" / "testing", args.count)
        if not 0 <= args.index < args.count:
            raise ValueError("shard index out of range")
        selected = [str(path.relative_to(ROOT)) for path in shards[args.index]]
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(f"canonical domain shard {args.index + 1}/{args.count}: {len(selected)} files", flush=True)
    return subprocess.call(
        [sys.executable, "-m", "pytest", "-q", "--noconftest",
         "-p", "pytest_asyncio.plugin", "--tb=short", "--maxfail=1", *selected],
        cwd=ROOT,
    )


if __name__ == "__main__":
    raise SystemExit(main())
