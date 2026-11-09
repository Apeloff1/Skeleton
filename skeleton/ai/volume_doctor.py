"""Shard doctor for the AI volume plane.

Shard 0 is measured. The 200-shard tree is not. This doctor refuses that claim.
"""

from __future__ import annotations

SHARD_LINES = 7_650_009
SHARD_BYTES = 303_339_093
SHARD_FUNCS = 850_000
SHARDS = 200
SAMPLE_MASS = 1.0392


def doctor() -> dict[str, object]:
    return {
        "plane": "ai",
        "shard": 0,
        "lines": SHARD_LINES,
        "bytes": SHARD_BYTES,
        "funcs": SHARD_FUNCS,
        "sample_mass": SAMPLE_MASS,
        "stored_prose": 0,
        "full_tree": False,
        "url": "pointer://ai/volume/shard0",
    }


def claim_full(shards_on_disk: int) -> dict[str, object]:
    if shards_on_disk != SHARDS:
        raise RuntimeError("full tree is not on disk")
    return {"full_tree": True, "shards": shards_on_disk}
