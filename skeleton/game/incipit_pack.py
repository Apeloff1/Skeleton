"""Named incipits."""

from __future__ import annotations

from typing import Any


class IncipitPackError(ValueError):
    pass


INCIPIT = tuple(f"in_{i:02d}" for i in range(8))


def open_(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in INCIPIT:
        raise IncipitPackError(name)
    nxt = dict(state)
    nxt["incipit"] = name
    nxt["opened"] = 1
    nxt["stored_prose"] = 0
    return nxt
