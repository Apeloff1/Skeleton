"""Named batches."""

from __future__ import annotations

from typing import Any


class BatchPackError(ValueError):
    pass


BATCH = tuple(f"bh_{i:02d}" for i in range(28))


def start(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BATCH:
        raise BatchPackError(name)
    nxt = dict(state)
    nxt["batch"] = name
    nxt["stored_prose"] = 0
    return nxt
