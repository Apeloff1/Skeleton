"""Named pipe rolls."""

from __future__ import annotations

from typing import Any


class PiperollPackError(ValueError):
    pass


PIPE = tuple(f"pr_{i:02d}" for i in range(12))


def enter(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in PIPE:
        raise PiperollPackError(name)
    nxt = dict(state)
    nxt["piperoll"] = name
    nxt["owed"] = int(nxt.get("owed", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
