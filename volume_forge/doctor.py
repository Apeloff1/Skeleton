"""Doctor. Missing organs fail closed. Full shard import is not this doctor."""

from __future__ import annotations

import json
from pathlib import Path

from volume_forge.catalog import HOUSES, ORGANS

def expected() -> int:
    return len(HOUSES) * len(ORGANS)

def missing(root: Path) -> list[str]:
    gone = []
    for house in HOUSES:
        for organ in ORGANS:
            if not (root / house / f"{organ}.py").is_file():
                gone.append(f"{house}/{organ}")
    return gone

def seal(root: Path, dest: Path) -> dict[str, object]:
    gone = missing(root)
    body = {"expected": expected(), "missing": gone, "ok": not gone, "stored_prose": 0, "clip": 1.1}
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(body, indent=2), encoding="utf-8")
    if gone:
        raise RuntimeError("missing organs")
    return body
