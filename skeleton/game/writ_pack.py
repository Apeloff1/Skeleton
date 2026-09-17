"""Named writs."""

from __future__ import annotations

from typing import Any


class WritPackError(ValueError):
    pass


WRIT = tuple(f"wr_{i:02d}" for i in range(12))


def issue(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in WRIT:
        raise WritPackError(name)
    nxt = dict(state)
    nxt["writ"] = name
    nxt["issued"] = 1
    nxt["stored_prose"] = 0
    return nxt
