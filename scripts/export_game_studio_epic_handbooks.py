"""Export up to 100 physically rendered Epic design manuals with SHA receipts.

Only exported files are ranked: virtual catalogue volume does not constitute
physical documents, external creativity ratings or completed playable games.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from skeleton.forge.game_frontier_studio_epic_handbooks import (
    BOOK_COUNT, EPIC_BOOK_PATHS, identity, receipt,
)


def export(root: Path, *, offset: int = 0, limit: int = 10) -> dict:
    if (type(offset) is not int or type(limit) is not int
            or not 0 <= offset < BOOK_COUNT or not 1 <= limit <= 100
            or offset + limit > BOOK_COUNT):
        raise ValueError("bounded Epic export requires 1..100 valid books")
    target = root.resolve()
    documents = []
    rankings = []
    for index in range(offset, offset + limit):
        row = receipt(*identity(index))
        markdown = row.pop("markdown")
        path = (target / EPIC_BOOK_PATHS[index]).resolve()
        if not path.is_relative_to(target):
            raise ValueError("Epic output path violates export boundary")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf8", newline="\n") as fd:
            fd.write(markdown)
        actual = sha256(path.read_bytes()).hexdigest()
        if actual != row["content_sha256"]:
            raise ValueError("Rendered Epic manuscript failed byte verification")
        documents.append(row)
        rankings.append({
            key: row[key] for key in (
                "path", "volume", "quality_score", "quality_kind",
                "words", "bytes", "content_sha256",
            )
        })
    ordered = {
        "quality": sorted(rankings, key=lambda d: (
            -d["quality_score"], -d["words"], d["path"])),
        "length": sorted(rankings, key=lambda d: (
            -d["words"], -d["quality_score"], d["path"])),
    }
    manifest = target / f"epic_manifest_{offset}_{offset+limit}.json"
    with manifest.open("x", encoding="utf8", newline="\n") as fd:
        json.dump({
            "schema": "skeleton.forge.epic_export_manifest.v1",
            "scope": "actually_exported_and_SHA_verified_only",
            "virtual_books": BOOK_COUNT,
            "range": [offset, offset + limit],
            "receipts": documents, "rankings": ordered,
        }, fd, sort_keys=True, indent=2)
        fd.write("\n")
    return {"manifest": str(manifest), "exported": len(documents),
            "virtual_books": BOOK_COUNT,
            "scope": "actually_exported_and_SHA_verified_only"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=10)
    params = parser.parse_args()
    print(json.dumps(export(params.out, offset=params.offset,
                            limit=params.limit), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
