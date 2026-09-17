"""Named clapper bridges."""

from __future__ import annotations

from typing import Any


class ClapperPackError(ValueError):
    pass


CLAP = tuple(f"cl_{i:02d}" for i in range(8))


def set_clap(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CLAP:
        raise ClapperPackError(name)
    nxt = dict(node)
    nxt["clapper"] = name
    nxt["stored_prose"] = 0
    return nxt
