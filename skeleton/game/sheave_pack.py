"""Named sheaves."""

from __future__ import annotations

from typing import Any


class SheavePackError(ValueError):
    pass


SHEAVE = tuple(f"sv_{i:02d}" for i in range(12))


def set_sheave(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SHEAVE:
        raise SheavePackError(name)
    nxt = dict(state)
    nxt["sheave"] = name
    nxt["stored_prose"] = 0
    return nxt
