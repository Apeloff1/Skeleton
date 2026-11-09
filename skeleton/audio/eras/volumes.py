"""Volume completion ledger. Honest gaps. No claim on occupied heads."""

from __future__ import annotations

VOLUMES = (
    {"id": "VOL-156", "path": "skeleton/audio/pipeline.py", "state": "main-one-file", "this_batch": 0},
    {"id": "VOL-156-batch", "path": "skeleton/audio/vol156", "state": "open-pr-3554", "this_batch": 0},
    {"id": "ERA-5120", "path": "skeleton/audio/eras", "state": "this-land", "this_batch": 5120},
)


def gaps() -> list[str]:
    return [
        "no sample decoder",
        "no copyrighted bank",
        "vol156 not merged",
        "pipeline.py not forked",
    ]
