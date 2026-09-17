"""Named naves."""

from __future__ import annotations

from typing import Any


class NavePackError(ValueError):
    pass


NAVE = tuple(f"nv_{i:02d}" for i in range(8))


def set_nave(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in NAVE:
        raise NavePackError(name)
    nxt = dict(state)
    nxt["nave"] = name
    nxt["stored_prose"] = 0
    return nxt
