"""Named grates."""

from __future__ import annotations

from typing import Any


class GratePackError(ValueError):
    pass


GRATE = tuple(f"gr_{i:02d}" for i in range(20))


def lift(node: dict[str, Any], state: dict[str, Any], name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if name not in GRATE:
        raise GratePackError(name)
    d, s = dict(node), dict(state)
    d["grate"] = name
    d["open"] = True
    d["stored_prose"] = 0
    s["stored_prose"] = 0
    return d, s
