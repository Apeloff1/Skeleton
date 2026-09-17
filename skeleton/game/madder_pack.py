"""Named madder lots."""

from __future__ import annotations

from typing import Any


class MadderPackError(ValueError):
    pass


MADDER = tuple(f"mr_{i:02d}" for i in range(12))


def steep(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in MADDER:
        raise MadderPackError(name)
    nxt = dict(state)
    nxt["madder"] = name
    nxt["stored_prose"] = 0
    return nxt
