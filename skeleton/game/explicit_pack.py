"""Named explicits."""

from __future__ import annotations

from typing import Any


class ExplicitPackError(ValueError):
    pass


EXPLICIT = tuple(f"ex_{i:02d}" for i in range(8))


def end(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in EXPLICIT:
        raise ExplicitPackError(name)
    nxt = dict(state)
    nxt["explicit"] = name
    nxt["ended"] = 1
    nxt["stored_prose"] = 0
    return nxt
