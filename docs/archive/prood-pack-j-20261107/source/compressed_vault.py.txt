"""Minimal compressed-vault stub for cold_storage (jsonl shards on disk).

Faithful surface of Prood ``core.compressed_vault`` used by cold_storage:
write_shard / read_shard / iter_shard / sample_shard / get_shard_entry /
list_shards / vault_stats. Uses plain JSONL (no zstd) so tests need no
native deps.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Iterator

_ROOT = Path(os.environ.get("PROOD_VAULT_DIR", "/tmp/skeleton-prood-vault"))
_ROOT.mkdir(parents=True, exist_ok=True)
_MANIFEST: dict[str, dict] = {}


def _path(name: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    return _ROOT / f"{safe}.jsonl"


def write_shard(name: str, rows, domain: str = "coll") -> dict:
    path = _path(name)
    count = 0
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, default=str) + "\n")
            count += 1
    entry = {
        "name": name, "path": str(path), "rows": count, "domain": domain,
        "bytes": path.stat().st_size, "created_at": time.time(),
    }
    _MANIFEST[name] = entry
    return entry


def iter_shard(name: str) -> Iterator[dict]:
    entry = _MANIFEST.get(name)
    path = Path(entry["path"]) if entry else _path(name)
    if not path.exists():
        return
        yield  # pragma: no cover
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def read_shard(name: str, limit: int = 50, offset: int = 0) -> list[dict]:
    out = []
    for i, row in enumerate(iter_shard(name)):
        if i < offset:
            continue
        out.append(row)
        if len(out) >= limit:
            break
    return out


def sample_shard(name: str, k: int = 5) -> list[dict]:
    out = []
    for row in iter_shard(name):
        out.append(row)
        if len(out) >= k:
            break
    return out


def list_shards() -> list[dict]:
    return list(_MANIFEST.values())


def get_shard_entry(name: str) -> dict | None:
    return _MANIFEST.get(name)


def vault_stats() -> dict:
    total_rows = sum(e.get("rows", 0) for e in _MANIFEST.values())
    total_bytes = sum(e.get("bytes", 0) for e in _MANIFEST.values())
    return {
        "shards": len(_MANIFEST), "rows": total_rows, "bytes": total_bytes,
        "root": str(_ROOT),
    }


def reset_vault() -> None:
    _MANIFEST.clear()
