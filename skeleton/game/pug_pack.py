"""Named pug mills."""

from __future__ import annotations

from typing import Any


class PugPackError(ValueError):
    pass


PUG = tuple(f"pg_{i:02d}" for i in range(12))


def mix(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in PUG:
        raise PugPackError(name)
    nxt = dict(state)
    nxt["pug"] = name
    nxt["clay"] = int(nxt.get("clay", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
