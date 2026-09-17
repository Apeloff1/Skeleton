"""Named pleas."""

from __future__ import annotations

from typing import Any


class PleaPackError(ValueError):
    pass


PLEA = tuple(f"pl_{i:02d}" for i in range(12))


def enter(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in PLEA:
        raise PleaPackError(name)
    nxt = dict(state)
    nxt["plea"] = name
    nxt["entered"] = 1
    nxt["stored_prose"] = 0
    return nxt
