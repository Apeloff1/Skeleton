"""Named retorts."""

from __future__ import annotations

from typing import Any


class RetortPackError(ValueError):
    pass


RETORT = tuple(f"rt_{i:02d}" for i in range(8))


def heat(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in RETORT:
        raise RetortPackError(name)
    nxt = dict(state)
    nxt["retort"] = name
    nxt["heat"] = min(16, int(nxt.get("heat", 0)) + 2)
    nxt["stored_prose"] = 0
    return nxt
