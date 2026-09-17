"""Named counterparts."""

from __future__ import annotations

from typing import Any


class CounterpartPackError(ValueError):
    pass


PART = tuple(f"cp_{i:02d}" for i in range(12))


def match(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in PART:
        raise CounterpartPackError(name)
    nxt = dict(state)
    nxt["counterpart"] = name
    nxt["fit"] = 1
    nxt["stored_prose"] = 0
    return nxt
