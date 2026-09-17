"""Named patrol routes."""

from __future__ import annotations

from typing import Any


class PatrolRouteError(ValueError):
    pass


ROUTES = tuple(f"route_{i:02d}" for i in range(30))


def step(agent: dict[str, Any], name: str, t: int) -> dict[str, Any]:
    if name not in ROUTES:
        raise PatrolRouteError(name)
    i = ROUTES.index(name)
    nxt = dict(agent)
    nxt["route"] = name
    nxt["room"] = f"f{i // 8}r{(t + i) % 8}"
    nxt["alert"] = int((t + i) % 5 == 0)
    nxt["stored_prose"] = 0
    return nxt


def home(agent: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in ROUTES:
        raise PatrolRouteError(name)
    i = ROUTES.index(name)
    nxt = dict(agent)
    nxt["route"] = name
    nxt["room"] = f"f{i // 8}r0"
    nxt["stored_prose"] = 0
    return nxt
