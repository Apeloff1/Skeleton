#!/usr/bin/env python3
"""Run existing Python unit-test files by product capability, without silent fallback.

This is a test-selection adapter, not another test framework. Filename selection
is deliberately conservative and does not constitute proof of feature coverage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from collections.abc import Iterable

ROOT = Path(__file__).resolve().parents[1]
TEST_ROOTS = ("tests", "skeleton/testing", "backend/tests")

# Keywords refer to test module filenames, not production files or imported code.
FEATURE_MARKERS: dict[str, tuple[str, ...]] = {
    "ai": ("ai", "inference", "model_routing", "transformer", "tokenizer", "embedding"),
    "jeeves": ("jeeves", "cortex", "llm"),
    "game-builder": ("game_builder", "game_forge", "story_canon", "forge", "world_builder", "dialogue"),
    "dragon": ("dragon", "crawler", "webcrawler"),
    "physics": ("physics", "simulation", "collision", "rigid_body", "broadphase"),
    "security": ("security", "sandbox", "auth", "authentication", "authorization", "isolation", "sast", "secret", "malware"),
    "shell": ("shell", "process_safety", "command", "terminal"),
    "memory": ("memory", "retrieval", "rag", "embedding", "vector", "chunker", "reranker"),
    "agents": ("agent", "agents", "swarm", "supervisor", "worker", "scheduler", "autonomous"),
    "provider": ("provider", "providers", "model_routing"),
    "app": ("app_assembly", "application", "installation", "app", "installer", "deployment"),
    "backend": (),  # All backend/tests test modules.
    "all": (),  # All three test roots, except opt-in integration categories.
}
FEATURE_DIRS: dict[str, tuple[str, ...]] = {
    "ai": ("tests/ai_pipeline",),
    "game-builder": ("tests/flgb",),
    "app": ("tests/application",),
    "agents": ("tests/shift_supervisor",),
    "security": ("tests/supply_chain",),
}
INTEGRATION_MARKERS = ("e2e", "integration", "live")


def _is_integration_case(relative: Path) -> bool:
    """Reject explicitly integration-designated files *and* directories."""
    return any(
        _has_marker(component.lower(), marker)
        for component in relative.with_suffix("").parts
        for marker in INTEGRATION_MARKERS
    )


def _has_marker(stem: str, marker: str) -> bool:
    """Match complete underscore-delimited tokens (avoid ai in 'mail')."""
    return re.search(rf"(?:^|_){re.escape(marker)}(?:_|$)", stem) is not None


def discover_tests(
    root: Path,
    features: Iterable[str],
    *,
    include_integration: bool = False,
) -> list[str]:
    """Return deterministic, de-duplicated repository-relative test paths."""
    selected = frozenset(features)
    unknown = selected.difference(FEATURE_MARKERS)
    if unknown:
        raise ValueError(f"unknown features: {', '.join(sorted(unknown))}")
    matches: set[str] = set()
    for test_root in TEST_ROOTS:
        directory = root / test_root
        if not directory.is_dir() or directory.is_symlink():
            continue
        canonical_root = directory.resolve()
        for path in directory.rglob("test_*.py"):
            # A symlinked intermediate directory must never escape the test root.
            if (not path.is_file() or path.is_symlink()
                    or not path.resolve().is_relative_to(canonical_root)):
                continue
            stem = path.stem.lower()
            relative_path = path.relative_to(root)
            relative = relative_path.as_posix()
            if not include_integration and _is_integration_case(relative_path):
                continue
            if (
                "all" in selected
                or ("backend" in selected and test_root == "backend/tests")
                or any(
                    _has_marker(stem, marker)
                    for feature in selected.difference({"all", "backend"})
                    for marker in FEATURE_MARKERS[feature]
                )
                or any(
                    relative.startswith(f"{folder}/")
                    for feature in selected.difference({"all", "backend"})
                    for folder in FEATURE_DIRS.get(feature, ())
                )
            ):
                matches.add(relative)
    return sorted(matches)



def parse_shard(value: str) -> tuple[int, int]:
    """Parse one-based INDEX/TOTAL without permitting zero or ambiguous syntax."""
    if not re.fullmatch(r"[1-9][0-9]*/[1-9][0-9]*", value):
        raise argparse.ArgumentTypeError("shard must use INDEX/TOTAL with positive integers")
    index, total = (int(part) for part in value.split("/"))
    if index > total:
        raise argparse.ArgumentTypeError("shard INDEX cannot exceed TOTAL")
    return index, total


def shard_paths(paths: list[str], shard: tuple[int, int] | None) -> list[str]:
    """Assign stable relative paths to disjoint shards, independent of PYTHONHASHSEED."""
    if shard is None:
        return list(paths)
    index, total = shard
    if total < 1 or not (1 <= index <= total):
        raise ValueError("invalid shard bounds")
    return [
        path for path in paths
        if int.from_bytes(hashlib.sha256(path.encode("utf-8")).digest(), "big") % total == index - 1
    ]


def selection_digest(paths: list[str]) -> str:
    """Hash the canonical, sorted JSON file list for reproducible selection evidence."""
    canonical = json.dumps(paths, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_command(paths: list[str], *, maxfail: int, junitxml: str | None) -> list[str]:
    if maxfail < 0:
        raise ValueError("maxfail must be non-negative")
    command = [
        sys.executable, "-m", "pytest", "-q", "--tb=short", "--strict-markers",
        "-p", "pytest_asyncio.plugin", f"--maxfail={maxfail}",
    ]
    if junitxml:
        command.append(f"--junitxml={junitxml}")
    command.extend(paths)
    return command


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--feature", action="append", required=True, choices=sorted(FEATURE_MARKERS),
        help="Select a feature; repeat to combine features.",
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--list", action="store_true", help="List files without importing tests.")
    modes.add_argument(
        "--list-json", action="store_true",
        help="Print a deterministic JSON selection manifest without importing tests.",
    )
    modes.add_argument(
        "--collect-only", action="store_true",
        help="Ask pytest to collect tests without executing them.",
    )
    parser.add_argument(
        "--include-integration", action="store_true",
        help="Opt in to files named e2e/integration/live (excluded by default).",
    )
    parser.add_argument(
        "--shard", type=parse_shard, metavar="INDEX/TOTAL",
        help="Run a stable, disjoint 1-based slice of the selected test files.",
    )
    parser.add_argument("--maxfail", type=int, default=1, help="Stop after N failures (0=all).")
    parser.add_argument(
        "--timeout-seconds", type=int, default=0,
        help="Limit subprocess wall time in seconds (0=no timeout).",
    )
    parser.add_argument("--junitxml", help="Write pytest JUnit XML to this path.")
    args = parser.parse_args(argv)
    if args.maxfail < 0:
        parser.error("--maxfail must be >= 0")
    if args.timeout_seconds < 0:
        parser.error("--timeout-seconds must be >= 0")

    paths = discover_tests(ROOT, args.feature, include_integration=args.include_integration)
    if not paths:
        print("ERROR: no matching test files; refusing a false-green run", file=sys.stderr)
        return 2
    # Each requested feature must be represented *before* sharding. A shard
    # may legitimately contain no tests from one of the selected features.
    feature_counts: dict[str, int] = {}
    for feature in sorted(set(args.feature)):
        count = len(paths) if feature == "all" else len(discover_tests(
            ROOT, (feature,), include_integration=args.include_integration
        ))
        feature_counts[feature] = count
        if count == 0:
            print(f"ERROR: no matching test files for {feature}; refusing a false-green run", file=sys.stderr)
            return 2
    pre_shard_count = len(paths)
    paths = shard_paths(paths, args.shard)
    if not paths:
        print("ERROR: selected shard has no test files; refusing a false-green run", file=sys.stderr)
        return 2
    if args.list_json:
        manifest = {
            "schema_version": 1,
            "features": sorted(set(args.feature)),
            "feature_file_counts_before_sharding": feature_counts,
            "include_integration": args.include_integration,
            "shard": (
                {"index": args.shard[0], "total": args.shard[1]}
                if args.shard is not None else None
            ),
            "pre_shard_file_count": pre_shard_count,
            "selected_file_count": len(paths),
            "selection_sha256": selection_digest(paths),
            "files": paths,
        }
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0
    if args.list:
        print("\n".join(paths))
        print(f"SELECTED {len(paths)} of {pre_shard_count} test files", file=sys.stderr)
        return 0

    env = os.environ.copy()
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env.pop("PYTEST_ADDOPTS", None)
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(ROOT), str(ROOT / "backend"), env.get("PYTHONPATH", "")])
    )
    command = build_command(paths, maxfail=args.maxfail, junitxml=args.junitxml)
    if args.collect_only:
        command.append("--collect-only")
    print(f"SELECTED {len(paths)} of {pre_shard_count} test files", flush=True)
    kwargs = {"cwd": ROOT, "env": env, "check": False}
    if args.timeout_seconds:
        kwargs["timeout"] = args.timeout_seconds
    try:
        return subprocess.run(command, **kwargs).returncode
    except subprocess.TimeoutExpired:
        print("ERROR: pytest exceeded the wall-time limit", file=sys.stderr)
        return 124
    except OSError as exc:
        print(f"ERROR: pytest could not start: {exc}", file=sys.stderr)
        return 126


if __name__ == "__main__":
    raise SystemExit(main())
