"""Named peat stacks."""

from __future__ import annotations

from typing import Any


class PeatstackPackError(ValueError):
    pass


STACK = tuple(f"ps_{i:02d}" for i in range(12))


def set_stack(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in STACK:
        raise PeatstackPackError(name)
    nxt = dict(state)
    have = list(nxt.get("peatstack") or [])
    have.append(name)
    nxt["peatstack"] = have
    nxt["stored_prose"] = 0
    return nxt
