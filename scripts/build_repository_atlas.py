#!/usr/bin/env python3
"""Build, verify, and query the complete Git-tree repository atlas.

Examples:
  python scripts/build_repository_atlas.py build --output /tmp/skeleton-atlas --near-limit 600
  python scripts/build_repository_atlas.py verify --output /tmp/skeleton-atlas
  python scripts/build_repository_atlas.py query --output /tmp/skeleton-atlas --text "jeeves quest editor"
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from skeleton.repo_intelligence.tree_atlas import (
    AtlasError, _json, build, query, write_index,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    sub = parser.add_subparsers(dest="command", required=True)
    for verb in ("build", "verify", "query"):
        command = sub.add_parser(verb)
        command.add_argument("--output", type=Path, required=True)
        if verb == "build":
            command.add_argument("--near-limit", type=int, default=600)
        if verb == "query":
            command.add_argument("--text", required=True)
            command.add_argument("--budget", type=int, default=3000)
            command.add_argument("--limit", type=int, default=25)
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve(strict=True)
        if args.command == "build":
            manifest, files, duplicates, near = build(root, near_limit=args.near_limit)
            write_index(args.output, manifest, files, duplicates, near)
            print(_json({"status": "built", "commit": manifest["commit"],
                         "files": manifest["blobs"], "features": manifest["feature_count"],
                         "exact_duplicate_groups": manifest["exact_duplicate_groups"],
                         "exact_duplicate_excess": manifest["exact_duplicate_excess"],
                         "near_duplicate_pairs": len(near["pairs"]),
                         "near_exhaustive": near["exhaustive"]}).strip())
            return 0
        if args.command == "query":
            print(_json(query(args.output, root, args.text,
                              budget=args.budget, limit=args.limit)).strip())
            return 0

        manifest, files, duplicates, _near = build(root, near_limit=0)
        existing = json.loads((args.output / "manifest.json").read_text(encoding="utf-8"))
        if manifest != existing:
            raise AtlasError("index manifest drift or stale source commit")
        expected_files = "".join(_json(f.json()) for f in files)
        expected_duplicates = "".join(_json(g) for g in duplicates)
        if (args.output / "files.jsonl").read_text(encoding="utf-8") != expected_files:
            raise AtlasError("indexed file identities differ from Git tree")
        if (args.output / "exact_duplicates.jsonl").read_text(encoding="utf-8") != expected_duplicates:
            raise AtlasError("indexed duplicates differ from Git tree")
        near = json.loads((args.output / "near_duplicates.json").read_text(encoding="utf-8"))
        if not isinstance(near.get("pairs"), list) or near.get("exhaustive") is not False:
            raise AtlasError("invalid near-duplicate disclosure")
        print(_json({"status": "verified", "commit": manifest["commit"],
                     "entries": len(files), "complete": True}).strip())
        return 0
    except (AtlasError, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"repository-atlas: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
