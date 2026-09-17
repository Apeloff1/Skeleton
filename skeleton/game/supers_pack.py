"""Named supers."""

from __future__ import annotations

from typing import Any


class SupersPackError(ValueError):
    pass


SUPER = tuple(f"su_{i:02d}" for i in range(12))


def add(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SUPER:
        raise SupersPackError(name)
    nxt = dict(state)
    have = list(nxt.get("supers") or [])
    have.append(name)
    nxt["supers"] = have
    nxt["stored_prose"] = 0
    return nxt
