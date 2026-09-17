"""Named stacks."""

from __future__ import annotations

from typing import Any


class StackPackError(ValueError):
    pass


STACK = tuple(f"sk_{i:02d}" for i in range(20))


def open_stack(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in STACK:
        raise StackPackError(name)
    nxt = dict(state)
    nxt["stack"] = name
    nxt["stored_prose"] = 0
    return nxt
