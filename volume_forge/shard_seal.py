"""Shard seal. Missing shards fail closed. Do not import an 85000-function file."""

from __future__ import annotations

from pathlib import Path

SHARDS = 200

def missing(root: Path) -> list[str]:
    return [f"shard_{i:03d}" for i in range(SHARDS) if not (root / f"shard_{i:03d}.py").is_file()]
