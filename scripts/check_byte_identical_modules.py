#!/usr/bin/env python3
"""Ratcheted inventory of byte-identical Python module twins (issue #80).

The consolidation program (#80) moved packages under new homes such as
``skeleton/ai/runtime/`` and ``skeleton/ai/research/`` while the old
``skeleton/<pkg>/`` copies stayed in place as full byte-for-byte clones.
Neither the contract-level duplicate inventory
(``check_legacy_duplicate_inventory.py``, #969) nor the filename shim
inventory (``check_compat_shim_inventory.py``, #1035) tracks *whole-file
clones*, so those twins can silently drift apart.

This checker hashes every tracked ``*.py`` file under ``SCAN_ROOTS`` and
groups files with identical content. The current set is frozen in a
baseline JSON file:

* ``--write-baseline`` records today's twin groups (run once, reviewed in PR).
* default (check) mode fails if a twin group appears that is not in the
  baseline, so new clones can't land unnoticed. Groups that shrink or vanish
  are reported as consolidation progress and never fail the run.

Read-only: it never deletes or rewrites source files. Stdlib only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = REPO_ROOT / "docs" / "consolidation" / "byte_identical_modules.baseline.json"

# Canonical tree only. ``satellites/branch-snapshots`` is frozen provenance
# and is deliberately out of scope.
SCAN_ROOTS: tuple[str, ...] = ("skeleton", "backend", "core", "scripts")
EXCLUDED_PARTS = frozenset({"__pycache__", "branch-snapshots", "fixtures"})
# Trivial files (empty packages, tiny stubs) are not meaningful clones.
MIN_BYTES = 200


def _tracked_files(root: Path, scan_roots: Sequence[str]) -> List[Path]:
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z", "--", *scan_roots],
            cwd=root, check=True, capture_output=True,
        ).stdout.decode()
        rels = [p for p in out.split("\0") if p]
    except (OSError, subprocess.CalledProcessError):
        rels = [
            str(p.relative_to(root))
            for r in scan_roots if (root / r).is_dir()
            for p in (root / r).rglob("*.py")
        ]
    return [root / r for r in rels if r.endswith(".py")]


def find_twin_groups(
    root: Path = REPO_ROOT,
    scan_roots: Sequence[str] = SCAN_ROOTS,
    min_bytes: int = MIN_BYTES,
    files: Iterable[Path] | None = None,
) -> Dict[str, List[str]]:
    """Return {sha256: sorted relative paths} for content shared by 2+ files."""
    by_hash: Dict[str, List[str]] = {}
    for path in files if files is not None else _tracked_files(root, scan_roots):
        rel = path.relative_to(root)
        if EXCLUDED_PARTS.intersection(rel.parts) or path.name == "__init__.py":
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if len(data) < min_bytes:
            continue
        by_hash.setdefault(hashlib.sha256(data).hexdigest(), []).append(rel.as_posix())
    return {h: sorted(p) for h, p in sorted(by_hash.items()) if len(p) > 1}


def _group_keys(groups: Dict[str, List[str]]) -> set[tuple[str, ...]]:
    # Keyed by path set, not hash: editing both twins identically is fine;
    # what matters is which files are clones of each other.
    return {tuple(paths) for paths in groups.values()}


def compare(current: Dict[str, List[str]], baseline: Dict[str, List[str]]) -> dict:
    """A current group is new unless every file in it was already cloned
    together in one baseline group (so shrinking groups never fail)."""
    cur, base = _group_keys(current), _group_keys(baseline)
    base_sets = [set(b) for b in base]
    new = sorted(g for g in cur if not any(set(g) <= b for b in base_sets))
    resolved = sorted(base - cur)
    return {"new": [list(g) for g in new], "resolved": [list(g) for g in resolved]}


def load_baseline(path: Path = BASELINE_PATH) -> Dict[str, List[str]]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())["groups"]


def write_baseline(groups: Dict[str, List[str]], path: Path = BASELINE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "issue": 80,
        "description": "Byte-identical Python module twins in the canonical tree.",
        "group_count": len(groups),
        "file_count": sum(len(p) for p in groups.values()),
        "groups": groups,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write-baseline", action="store_true")
    ap.add_argument("--json", action="store_true", help="print the comparison as JSON")
    args = ap.parse_args(argv)

    groups = find_twin_groups()
    if args.write_baseline:
        write_baseline(groups)
        print(f"wrote {BASELINE_PATH.relative_to(REPO_ROOT)}: {len(groups)} groups")
        return 0

    result = compare(groups, load_baseline())
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"byte-identical twin groups: {len(groups)}")
        for g in result["resolved"]:
            print(f"  resolved (progress): {', '.join(g)}")
        for g in result["new"]:
            print(f"  NEW clone group: {', '.join(g)}")
    if result["new"]:
        print("FAIL: new byte-identical module clones; import from the canonical "
              "module or re-export instead of copying.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
