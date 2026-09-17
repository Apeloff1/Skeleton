"""Named fine rolls."""

from __future__ import annotations

from typing import Any


class FinerollPackError(ValueError):
    pass


FINE = tuple(f"fn_{i:02d}" for i in range(12))


def enter(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in FINE:
        raise FinerollPackError(name)
    nxt = dict(state)
    nxt["fineroll"] = name
    nxt["fine"] = max(0, int(n))
    nxt["stored_prose"] = 0
    return nxt
