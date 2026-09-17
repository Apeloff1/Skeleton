"""Named courier routes."""

from __future__ import annotations

from typing import Any


class CourierPackError(ValueError):
    pass


ROUTES = tuple(f"cr_{i:02d}" for i in range(20))


def go(state: dict[str, Any], name: str, dest: str) -> dict[str, Any]:
    if name not in ROUTES:
        raise CourierPackError(name)
    nxt = dict(state)
    nxt["courier"] = name
    nxt["room"] = dest
    nxt["stored_prose"] = 0
    return nxt
