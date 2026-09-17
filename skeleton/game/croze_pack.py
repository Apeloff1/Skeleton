"""Named crozes."""

from __future__ import annotations

from typing import Any


class CrozePackError(ValueError):
    pass


CROZE = tuple(f"cz_{i:02d}" for i in range(12))


def cut(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CROZE:
        raise CrozePackError(name)
    nxt = dict(state)
    nxt["croze"] = name
    nxt["groove"] = 1
    nxt["stored_prose"] = 0
    return nxt
