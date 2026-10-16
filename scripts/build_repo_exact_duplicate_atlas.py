#!/usr/bin/env python3
"""Write a full, read-only, content-addressed Git duplicate candidate atlas."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile

from skeleton.repo_intelligence import GitIndex, build_exact_duplicate_atlas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    target = args.output.expanduser().absolute()
    if (target.is_symlink() or not target.parent.is_dir()
            or (target.exists() and not args.overwrite)):
        parser.error("output directory must exist; destination must not be a symlink or overwritten implicitly")
    # GitIndex has pinned-head/index stability guards, bounded byte/file/time
    # ceilings and symlink-safe read-only hashing. Do not build a second walker.
    snapshot = GitIndex(args.root).snapshot()
    atlas = build_exact_duplicate_atlas(snapshot)
    payload = (json.dumps(atlas.to_dict(), sort_keys=True, indent=2, ensure_ascii=False)
               + "\n").encode("utf-8")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=".atlas-", suffix=".json",
            dir=target.parent, delete=False,
        ) as output:
            temporary = output.name
            output.write(payload)
        if args.overwrite:
            os.replace(temporary, target)
        else:
            os.link(temporary, target)  # atomic no-clobber publish
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    print(
        f"atlas source={atlas.head} paths={atlas.tracked_files} "
        f"duplicate_clusters={len(atlas.clusters)} candidates={atlas.duplicate_file_paths}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
