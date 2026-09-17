"""Named polls."""

from __future__ import annotations

from typing import Any


class PollPackError(ValueError):
    pass


POLL = tuple(f"po_{i:02d}" for i in range(12))


def count(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in POLL:
        raise PollPackError(name)
    nxt = dict(state)
    nxt["poll"] = name
    nxt["heads"] = max(0, int(n))
    nxt["stored_prose"] = 0
    return nxt
