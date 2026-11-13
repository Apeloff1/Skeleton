"""Export bounded actual continuity manuscripts with SHA-256 receipts."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from skeleton.forge.game_frontier_studio_continuity_handbooks import (
    BOOK_COUNT, CONTINUITY_BOOK_PATHS, identity, receipt,
)


def export(destination: Path, *, offset: int = 0, limit: int = 32) -> dict:
    if (type(offset) is not int or type(limit) is not int
            or not 0 <= offset < BOOK_COUNT
            or not 1 <= limit <= 100 or offset + limit > BOOK_COUNT):
        raise ValueError("continuity exporter requires 1-100 valid book identities")
    root = destination.resolve()
    items = []
    metrics = []
    for index in range(offset, offset + limit):
        entry = receipt(*identity(index))
        document = entry.pop("markdown")
        path = (root / CONTINUITY_BOOK_PATHS[index]).resolve()
        if not path.is_relative_to(root):
            raise ValueError("continuity source path escapes export root")
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise FileExistsError("refusing to overwrite an existing manuscript")
        with path.open("x", encoding="utf8", newline="\n") as output:
            output.write(document)
        if sha256(path.read_bytes()).hexdigest() != entry["content_sha256"]:
            raise ValueError("continuity export SHA-256 mismatch")
        items.append(entry)
        metrics.append({
            key: entry[key] for key in (
                "path", "volume", "continuity", "quality_score",
                "words", "bytes", "content_sha256")
        })
    manifest = root / f"continuity_manifest_{offset}_{offset + limit}.json"
    ranking = {
        "quality": sorted(metrics, key=lambda row: (
            -row["quality_score"], -row["words"], row["path"])),
        "length": sorted(metrics, key=lambda row: (
            -row["words"], -row["quality_score"], row["path"])),
    }
    payload = {
        "schema": "skeleton.forge.continuity_export_manifest.v1",
        "catalog": BOOK_COUNT, "scope": "actual_exported_batch_only",
        "range": [offset, offset + limit], "receipts": items, "ranking": ranking,
    }
    with manifest.open("x", encoding="utf8", newline="\n") as output:
        output.write(json.dumps(payload, sort_keys=True,
                                indent=2, ensure_ascii=False) + "\n")
    return {"catalog": BOOK_COUNT, "exported": len(items),
            "manifest": str(manifest), "scope": "actual_exported_batch_only"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=32)
    options = parser.parse_args()
    print(json.dumps(export(options.out, offset=options.offset,
                            limit=options.limit), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
