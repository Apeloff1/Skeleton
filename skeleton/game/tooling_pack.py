"""Named tooling."""

from __future__ import annotations

from typing import Any


class ToolingPackError(ValueError):
    pass


TOOL = tuple(f"tl_{i:02d}" for i in range(12))


def stamp(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in TOOL:
        raise ToolingPackError(name)
    nxt = dict(state)
    nxt["tooling"] = name
    nxt["stamped"] = 1
    nxt["stored_prose"] = 0
    return nxt
