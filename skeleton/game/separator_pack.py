"""Named separators."""

from __future__ import annotations

from typing import Any


class SeparatorPackError(ValueError):
    pass


SEP = tuple(f"sp_{i:02d}" for i in range(8))


def spin(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SEP:
        raise SeparatorPackError(name)
    nxt = dict(state)
    nxt["separator"] = name
    nxt["spin"] = int(nxt.get("spin", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
