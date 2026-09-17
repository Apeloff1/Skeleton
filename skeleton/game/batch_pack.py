"""Named brick batches."""

from __future__ import annotations

from typing import Any


class BatchPackError(ValueError):
    pass


BATCH = tuple(f"bt_{i:02d}" for i in range(16))


def set_batch(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in BATCH:
        raise BatchPackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("batch") or {})
    cur[name] = max(0, int(n))
    nxt["batch"] = cur
    nxt["stored_prose"] = 0
    return nxt
