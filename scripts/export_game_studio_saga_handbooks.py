"""Export bounded batches of real Saga technical manuscripts and SHA-256 receipts.

The 900M book catalogue is virtual. Only physically rendered, integrity-
checked files in this invocation are included in objective/length rankings.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from skeleton.forge.game_frontier_studio_saga_handbooks import (
    BOOK_COUNT, SAGA_BOOK_PATHS, identity, receipt,
)


def export(destination: Path, *, offset: int = 0, limit: int = 32) -> dict:
    if (type(offset) is not int or type(limit) is not int
            or not 0 <= offset < BOOK_COUNT or not 1 <= limit <= 100
            or offset + limit > BOOK_COUNT):
        raise ValueError("Saga export needs exact source indices and 1..100 books")
    root = destination.resolve()
    documents = []
    scores = []
    for index in range(offset, offset + limit):
        entry = receipt(*identity(index))
        markdown = entry.pop("markdown")
        path = (root / SAGA_BOOK_PATHS[index]).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Saga handbook destination escapes allowed export root")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf8", newline="\n") as stream:
            stream.write(markdown)
        if sha256(path.read_bytes()).hexdigest() != entry["content_sha256"]:
            raise ValueError("Exported Saga book SHA mismatch")
        documents.append(entry)
        scores.append({
            field: entry[field] for field in (
                "path", "volume", "quality_score", "words", "bytes", "content_sha256"
            )
        })
    ranking = {
        "quality": sorted(scores, key=lambda d: (
            -d["quality_score"], -d["words"], d["path"])),
        "length": sorted(scores, key=lambda d: (
            -d["words"], -d["quality_score"], d["path"])),
    }
    manifest = root / f"saga_manifest_{offset}_{offset + limit}.json"
    with manifest.open("x", encoding="utf8", newline="\n") as stream:
        json.dump({
            "schema": "skeleton.forge.saga_export_manifest.v1",
            "scope": "actually_exported_verified_batch_only",
            "catalog": BOOK_COUNT,
            "range": [offset, offset + limit],
            "receipts": documents,
            "ranking": ranking,
        }, stream, sort_keys=True, indent=2)
        stream.write("\n")
    return {
        "catalog": BOOK_COUNT, "exported": len(documents),
        "manifest": str(manifest),
        "scope": "actually_exported_verified_batch_only",
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
