"""Materialize source-derived temporal handbooks with exact receipts and rankings."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from skeleton.forge.game_frontier_studio_epoch_handbooks import (
    BOOK_COUNT, EPOCH_BOOK_PATHS, identity, receipt,
)


def export(destination: Path, *, offset: int = 0, limit: int = 32) -> dict:
    if (type(offset) is not int or type(limit) is not int
            or not 0 <= offset < BOOK_COUNT or not 1 <= limit <= 100
            or offset + limit > BOOK_COUNT):
        raise ValueError("export requires a bounded 1..100 exact epoch book range")
    root = destination.resolve()
    files, rankings = [], []
    for index in range(offset, offset + limit):
        item = receipt(*identity(index))
        body = item.pop("markdown")
        target = (root / EPOCH_BOOK_PATHS[index]).resolve()
        if not target.is_relative_to(root):
            raise ValueError("book destination escapes export root")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf8", newline="\n") as stream:
            stream.write(body)
        if sha256(target.read_bytes()).hexdigest() != item["content_sha256"]:
            raise ValueError("persisted epoch handbook failed byte-level SHA verification")
        files.append(item)
        rankings.append({
            k: item[k] for k in
            ("path", "volume", "quality_score", "words", "bytes", "content_sha256")
        })
    ranking = {
        "quality": sorted(rankings, key=lambda row: (
            -row["quality_score"], -row["words"], row["path"])),
        "length": sorted(rankings, key=lambda row: (
            -row["words"], -row["quality_score"], row["path"])),
    }
    manifest = root / f"epoch_manifest_{offset}_{offset+limit}.json"
    with manifest.open("x", encoding="utf8", newline="\n") as stream:
        json.dump({
            "schema": "skeleton.forge.epoch_export_manifest.v1",
            "scope": "actually_materialized_batch_only",
            "catalog": BOOK_COUNT, "range": [offset, offset + limit],
            "receipts": files, "ranking": ranking,
        }, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return {
        "catalog": BOOK_COUNT, "exported": len(files),
        "manifest": str(manifest), "scope": "actually_materialized_batch_only",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=32)
    args = parser.parse_args()
    print(json.dumps(export(args.out, offset=args.offset, limit=args.limit),
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
